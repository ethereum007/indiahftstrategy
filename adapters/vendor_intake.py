from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import asdict, dataclass, fields
from datetime import datetime, timezone
from numbers import Real
from pathlib import Path
from typing import Any, Mapping

import pandas as pd

from adapters.broker import adapter_schema_status, get_adapter
from adapters.schema_audit import SCHEMA_KIND_ATTRS
from reports.manifest import (
    MANIFEST_NAME,
    file_sha256,
    verify_experiment_manifest,
    write_experiment_manifest,
)


AUTO_KINDS = ("ticks", "chain", "orders", "fills")
RUN_TYPE = "vendor_csv_intake"
CONTRACT_VERSION = "vendor_csv_intake/v1"
COLUMNS_FILE = "vendor_intake_columns.csv"
KIND_SCORES_FILE = "vendor_intake_kind_scores.csv"
MAPPING_CANDIDATES_FILE = "vendor_intake_mapping_candidates.csv"
SOURCE_PROFILE_FILE = "vendor_intake_source_profile.json"
SUMMARY_FILE = "vendor_intake_summary.csv"
ACTION_QUEUE_FILE = "vendor_intake_action_queue.csv"
CONFIG_FILE = "vendor_intake_config.json"
RUNBOOK_FILE = "vendor_intake_runbook.md"
RECEIPT_FILE = "vendor_intake_receipt.json"
STATIC_ARTIFACTS = (
    COLUMNS_FILE,
    KIND_SCORES_FILE,
    MAPPING_CANDIDATES_FILE,
    SOURCE_PROFILE_FILE,
    SUMMARY_FILE,
    ACTION_QUEUE_FILE,
    CONFIG_FILE,
    RUNBOOK_FILE,
    RECEIPT_FILE,
)
SAFETY_FALSE_FIELDS = (
    "provider_network_called",
    "credential_environment_read",
    "credential_values_stored",
    "normalization_executed",
    "strategy_research_enabled",
    "broker_api_called",
    "routing_enabled",
    "submission_enabled",
    "authorizes_submission",
)
SAFETY_TRUE_FIELDS = (
    "intake_only",
    "deterministic_reconstruction",
    "source_fingerprint_required",
    "mapping_review_required",
    "requires_real_vendor_schema_review",
)


@dataclass(frozen=True)
class VendorCsvIntakeConfig:
    adapter: str = "arrow_money"
    kind: str = "auto"
    sample_rows: int = 1000
    min_mapping_coverage: float = 1.0
    output_mapping_file: str = "vendor_mapping_draft.csv"


@dataclass(frozen=True)
class VendorCsvIntakeReport:
    columns: pd.DataFrame
    kind_scores: pd.DataFrame
    mapping_candidates: pd.DataFrame
    mapping_draft: pd.DataFrame
    summary: pd.DataFrame
    source_profile: dict[str, Any] | None = None
    output_dir: Path | None = None
    action_queue: pd.DataFrame | None = None
    receipt: dict[str, Any] | None = None
    config_payload: dict[str, Any] | None = None

    @property
    def ready(self) -> bool:
        if self.summary.empty:
            return False
        return bool(self.summary.iloc[0]["ready"])


@dataclass(frozen=True)
class VendorCsvIntakeVerification:
    verified: bool
    ready: bool
    blocked: bool
    manifest_current: bool
    source_current: bool
    artifacts_consistent: bool
    intake_only: bool
    non_authorizing: bool
    output_dir: Path
    source_path: Path | None = None
    error: str = ""


def profile_vendor_csv(
    sample: pd.DataFrame,
    *,
    sample_path: str | Path | None = None,
    config: VendorCsvIntakeConfig | None = None,
) -> VendorCsvIntakeReport:
    config = config or VendorCsvIntakeConfig()
    _validate_config(config)
    source_columns = [str(column) for column in sample.columns]
    if not source_columns:
        raise ValueError("vendor CSV sample has no columns")

    columns = _column_profiles(sample, source_columns)
    source_profile = _source_profile(sample, source_columns, sample_path)
    kinds = _candidate_kinds(config.kind)
    candidates = pd.concat(
        [_mapping_candidates(source_columns, kind, config.adapter) for kind in kinds],
        ignore_index=True,
    )
    kind_scores = _kind_scores(candidates, config)
    best_kind = str(kind_scores.iloc[0]["kind"])
    mapping_draft = _draft_for_kind(candidates, best_kind)
    summary = _summary(
        columns=columns,
        kind_scores=kind_scores,
        mapping_draft=mapping_draft,
        sample=sample,
        source_path=str(sample_path or ""),
        source_profile=source_profile,
        config=config,
    )
    action_queue = _action_queue(summary.iloc[0], mapping_draft)
    return VendorCsvIntakeReport(
        columns=columns,
        kind_scores=kind_scores,
        mapping_candidates=candidates,
        mapping_draft=mapping_draft,
        summary=summary,
        source_profile=source_profile,
        action_queue=action_queue,
    )


def write_vendor_csv_intake_report(
    sample_path: str | Path,
    *,
    output_dir: str | Path,
    config: VendorCsvIntakeConfig | None = None,
) -> VendorCsvIntakeReport:
    config = config or VendorCsvIntakeConfig()
    _validate_config(config)
    sample_file = Path(sample_path).resolve()
    if not sample_file.is_file():
        raise FileNotFoundError(f"vendor CSV sample not found: {sample_file}")
    out = Path(output_dir).resolve()
    if out.exists():
        raise FileExistsError(f"vendor CSV intake output already exists: {out}")
    if out in sample_file.parents:
        raise ValueError("vendor CSV sample cannot be stored inside the intake output")

    source_sha256 = file_sha256(sample_file)
    source_size_bytes = int(sample_file.stat().st_size)
    sample = pd.read_csv(sample_file, nrows=config.sample_rows)
    _require_source_unchanged(sample_file, source_sha256, source_size_bytes)
    report = _assemble_persisted_report(
        sample,
        sample_file=sample_file,
        output_dir=out,
        config=config,
        recorded_at_utc=datetime.now(timezone.utc).isoformat(),
    )

    out.mkdir(parents=True)
    mapping_path = out / config.output_mapping_file
    _write_csv(report.columns, out / COLUMNS_FILE)
    _write_csv(report.kind_scores, out / KIND_SCORES_FILE)
    _write_csv(report.mapping_candidates, out / MAPPING_CANDIDATES_FILE)
    _write_csv(report.mapping_draft, mapping_path)
    _write_csv(report.summary, out / SUMMARY_FILE)
    report_action_queue = (
        report.action_queue if report.action_queue is not None else pd.DataFrame()
    )
    _write_csv(report_action_queue, out / ACTION_QUEUE_FILE)
    _write_json(out / SOURCE_PROFILE_FILE, report.source_profile or {})
    _write_json(out / RECEIPT_FILE, report.receipt or {})
    _write_json(out / CONFIG_FILE, report.config_payload or {})
    (out / RUNBOOK_FILE).write_text(
        _runbook_markdown(report.summary.iloc[0], report_action_queue),
        encoding="utf-8",
    )
    _require_source_unchanged(sample_file, source_sha256, source_size_bytes)
    write_experiment_manifest(
        out,
        run_type=RUN_TYPE,
        parameters={"config": asdict(config)},
        inputs={"sample": sample_file},
        extra=_manifest_extra(report),
    )
    _require_source_unchanged(sample_file, source_sha256, source_size_bytes)
    return report


def verify_vendor_csv_intake_report(
    intake_dir: str | Path,
) -> VendorCsvIntakeVerification:
    candidate = Path(intake_dir)
    root = candidate.parent if candidate.is_file() else candidate
    root = root.resolve()
    manifest_path = root / MANIFEST_NAME
    source_path: Path | None = None
    source_current = False
    integrity = verify_experiment_manifest(
        manifest_path,
        expected_run_type=RUN_TYPE,
        required_artifacts=STATIC_ARTIFACTS,
        require_input_fingerprints=True,
    )
    try:
        manifest = _read_json(manifest_path, "vendor intake manifest")
        config = _config_from_manifest(manifest)
        integrity = verify_experiment_manifest(
            manifest_path,
            expected_run_type=RUN_TYPE,
            required_artifacts=(*STATIC_ARTIFACTS, config.output_mapping_file),
            require_input_fingerprints=True,
        )
        source_path = _manifest_sample_path(manifest)
        source_current = _manifest_sample_current(manifest, source_path)
        if not source_current:
            return _failed_verification(
                root,
                source_path=source_path,
                manifest_current=integrity.passed,
                source_current=False,
                error="vendor source fingerprint is stale",
            )

        actual_receipt = _read_json(root / RECEIPT_FILE, "vendor intake receipt")
        sample = pd.read_csv(source_path, nrows=config.sample_rows)
        expected = _assemble_persisted_report(
            sample,
            sample_file=source_path,
            output_dir=root,
            config=config,
            recorded_at_utc=_text(actual_receipt.get("recorded_at_utc")),
        )
        actual_summary = _read_csv(root / SUMMARY_FILE, "vendor intake summary")
        actual_summary_row = _single_row(actual_summary, "vendor intake summary")
        actual_action_queue = _read_csv(root / ACTION_QUEUE_FILE, "vendor intake action queue")
        actual_source_profile = _read_json(root / SOURCE_PROFILE_FILE, "vendor intake source profile")
        actual_config = _read_json(root / CONFIG_FILE, "vendor intake config")
        actual_runbook = (root / RUNBOOK_FILE).read_text(encoding="utf-8")
        artifacts_consistent = bool(
            _dataframe_records_equal(_read_csv(root / COLUMNS_FILE, "vendor intake columns"), expected.columns)
            and _dataframe_records_equal(_read_csv(root / KIND_SCORES_FILE, "vendor intake kind scores"), expected.kind_scores)
            and _dataframe_records_equal(
                _read_csv(root / MAPPING_CANDIDATES_FILE, "vendor intake mapping candidates"),
                expected.mapping_candidates,
            )
            and _dataframe_records_equal(
                _read_csv(root / config.output_mapping_file, "vendor mapping draft"),
                expected.mapping_draft,
            )
            and _dataframe_records_equal(actual_summary, expected.summary)
            and _dataframe_records_equal(
                actual_action_queue,
                expected.action_queue
                if expected.action_queue is not None
                else pd.DataFrame(),
            )
            and _jsonable(actual_source_profile) == _jsonable(expected.source_profile)
            and _jsonable(actual_receipt) == _jsonable(expected.receipt)
            and _jsonable(actual_config) == _jsonable(expected.config_payload)
            and actual_runbook
            == _runbook_markdown(
                expected.summary.iloc[0],
                expected.action_queue
                if expected.action_queue is not None
                else pd.DataFrame(),
            )
            and _jsonable(manifest.get("parameters")) == {"config": _jsonable(asdict(config))}
            and _jsonable(manifest.get("extra")) == _jsonable(_manifest_extra(expected))
            and _manifest_input_contract_current(manifest, source_path)
        )
        intake_only = _surfaces_intake_only(
            actual_summary_row,
            actual_receipt,
            actual_config,
            _mapping(manifest.get("extra")),
        )
        non_authorizing = _surfaces_non_authorizing(
            actual_summary_row,
            actual_receipt,
            actual_config,
            _mapping(manifest.get("extra")),
        )
        ready = bool(expected.ready)
        verified = bool(
            integrity.passed
            and source_current
            and artifacts_consistent
            and intake_only
            and non_authorizing
        )
        return VendorCsvIntakeVerification(
            verified=verified,
            ready=ready,
            blocked=bool(verified and not ready),
            manifest_current=integrity.passed,
            source_current=source_current,
            artifacts_consistent=artifacts_consistent,
            intake_only=intake_only,
            non_authorizing=non_authorizing,
            output_dir=root,
            source_path=source_path,
            error="" if verified else (integrity.error or "vendor intake semantic verification failed"),
        )
    except (OSError, ValueError, KeyError, TypeError, pd.errors.ParserError) as exc:
        return _failed_verification(
            root,
            source_path=source_path,
            manifest_current=integrity.passed,
            source_current=source_current,
            error=str(exc),
        )


def _assemble_persisted_report(
    sample: pd.DataFrame,
    *,
    sample_file: Path,
    output_dir: Path,
    config: VendorCsvIntakeConfig,
    recorded_at_utc: str,
) -> VendorCsvIntakeReport:
    base = profile_vendor_csv(sample, sample_path=sample_file, config=config)
    mapping_path = output_dir / config.output_mapping_file
    mapping_sha256 = _csv_sha256(base.mapping_draft)
    source_profile = _with_mapping_profile(
        base.source_profile or {},
        mapping_path,
        mapping_sha256=mapping_sha256,
    )
    summary = base.summary.copy()
    summary["contract_version"] = CONTRACT_VERSION
    summary["mapping_draft_sha256"] = mapping_sha256
    for field, value in _safety_payload().items():
        summary[field] = value
    summary["non_authorizing"] = True
    action_queue = _action_queue(summary.iloc[0], base.mapping_draft)
    receipt = _receipt(
        summary.iloc[0],
        source_profile=source_profile,
        config=config,
        recorded_at_utc=recorded_at_utc,
    )
    summary["intake_receipt_id"] = receipt["intake_receipt_id"]
    config_payload = _config(summary.iloc[0], action_queue, config, receipt=receipt)
    return VendorCsvIntakeReport(
        columns=base.columns,
        kind_scores=base.kind_scores,
        mapping_candidates=base.mapping_candidates,
        mapping_draft=base.mapping_draft,
        summary=summary,
        source_profile=source_profile,
        output_dir=output_dir,
        action_queue=action_queue,
        receipt=receipt,
        config_payload=config_payload,
    )


def _receipt(
    summary_row: pd.Series,
    *,
    source_profile: dict[str, Any],
    config: VendorCsvIntakeConfig,
    recorded_at_utc: str,
) -> dict[str, Any]:
    core = {
        "schema_version": 1,
        "contract_version": CONTRACT_VERSION,
        "receipt_type": "non_authorizing_vendor_csv_intake",
        "recorded_at_utc": _utc_text(recorded_at_utc),
        "source": _jsonable(source_profile),
        "mapping": {
            "draft_file": config.output_mapping_file,
            "draft_sha256": _text(source_profile.get("mapping_draft_sha256")),
            "requested_kind": config.kind,
            "best_kind": _text(summary_row.get("best_kind")),
            "required_columns": _int(summary_row.get("required_columns")),
            "mapped_columns": _int(summary_row.get("mapped_columns")),
            "unmapped_required_columns": _int(summary_row.get("unmapped_required_columns")),
            "coverage": _float(summary_row.get("mapping_coverage")),
            "min_coverage": float(config.min_mapping_coverage),
        },
        "outcome": {
            "ready": _to_bool(summary_row.get("ready", False)),
            "blocked": not _to_bool(summary_row.get("ready", False)),
            "selected_kind_ambiguous": _to_bool(summary_row.get("selected_kind_ambiguous", False)),
            "failed_check_count": _int(summary_row.get("failed_check_count")),
            "failed_check_names": _split_items(summary_row.get("failed_check_names")),
            "blocked_action_count": _int(summary_row.get("blocked_action_count")),
            "recommendation": _text(summary_row.get("recommendation")),
        },
        "settings": _jsonable(asdict(config)),
        "safety": _safety_payload(),
    }
    receipt_sha256 = _canonical_sha256(core)
    return {
        **core,
        "intake_receipt_id": f"vendor-intake-{receipt_sha256[:24]}",
        "intake_receipt_sha256": receipt_sha256,
    }


def _manifest_extra(report: VendorCsvIntakeReport) -> dict[str, Any]:
    receipt = report.receipt or {}
    return {
        "contract_version": CONTRACT_VERSION,
        "intake_receipt_id": _text(receipt.get("intake_receipt_id")),
        "source_profile": _jsonable(report.source_profile or {}),
        "outcome": _jsonable(_mapping(receipt.get("outcome"))),
        "safety": _safety_payload(),
    }


def _safety_payload() -> dict[str, bool]:
    return {
        **{field: False for field in SAFETY_FALSE_FIELDS},
        **{field: True for field in SAFETY_TRUE_FIELDS},
    }


def _surfaces_intake_only(*surfaces: Mapping[str, Any]) -> bool:
    return all(
        all(_explicit_bool(_safety_surface(surface).get(field)) for field in SAFETY_TRUE_FIELDS)
        for surface in surfaces
    )


def _surfaces_non_authorizing(*surfaces: Mapping[str, Any]) -> bool:
    return all(
        all(not _explicit_bool(_safety_surface(surface).get(field), default=True) for field in SAFETY_FALSE_FIELDS)
        for surface in surfaces
    )


def _safety_surface(surface: Mapping[str, Any]) -> Mapping[str, Any]:
    safety = surface.get("safety")
    return safety if isinstance(safety, Mapping) else surface


def _explicit_bool(value: Any, *, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    return _to_bool(value, default=default)


def _config_from_manifest(manifest: Mapping[str, Any]) -> VendorCsvIntakeConfig:
    parameters = _mapping(manifest.get("parameters"))
    payload = _mapping(parameters.get("config"))
    expected_fields = {field.name for field in fields(VendorCsvIntakeConfig)}
    if set(payload) != expected_fields:
        raise ValueError("vendor intake manifest config contract is incomplete or has unknown fields")
    config = VendorCsvIntakeConfig(
        adapter=str(payload["adapter"]),
        kind=str(payload["kind"]),
        sample_rows=int(payload["sample_rows"]),
        min_mapping_coverage=float(payload["min_mapping_coverage"]),
        output_mapping_file=str(payload["output_mapping_file"]),
    )
    _validate_config(config)
    return config


def _manifest_sample_path(manifest: Mapping[str, Any]) -> Path:
    inputs = _mapping(manifest.get("inputs"))
    sample = _mapping(inputs.get("sample"))
    if sample.get("kind") != "file" or not sample.get("path"):
        raise ValueError("vendor intake manifest lacks a file sample fingerprint")
    return Path(str(sample["path"])).resolve()


def _manifest_sample_current(manifest: Mapping[str, Any], source_path: Path) -> bool:
    inputs = _mapping(manifest.get("inputs"))
    sample = _mapping(inputs.get("sample"))
    return bool(
        source_path.is_file()
        and Path(str(sample.get("path", ""))).resolve() == source_path
        and _int(sample.get("size_bytes")) == int(source_path.stat().st_size)
        and _text(sample.get("sha256")) == file_sha256(source_path)
    )


def _manifest_input_contract_current(manifest: Mapping[str, Any], source_path: Path) -> bool:
    inputs = _mapping(manifest.get("inputs"))
    return set(inputs) == {"sample"} and _manifest_sample_current(manifest, source_path)


def _failed_verification(
    root: Path,
    *,
    source_path: Path | None,
    manifest_current: bool,
    source_current: bool,
    error: str,
) -> VendorCsvIntakeVerification:
    return VendorCsvIntakeVerification(
        verified=False,
        ready=False,
        blocked=False,
        manifest_current=manifest_current,
        source_current=source_current,
        artifacts_consistent=False,
        intake_only=False,
        non_authorizing=False,
        output_dir=root,
        source_path=source_path,
        error=error,
    )


def _require_source_unchanged(path: Path, sha256: str, size_bytes: int) -> None:
    if (
        not path.is_file()
        or int(path.stat().st_size) != size_bytes
        or file_sha256(path) != sha256
    ):
        raise RuntimeError("vendor CSV source changed during intake")


def _write_csv(frame: pd.DataFrame, path: Path) -> None:
    path.write_bytes(frame.to_csv(index=False, lineterminator="\n").encode("utf-8"))


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.write_text(
        json.dumps(_jsonable(payload), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _csv_sha256(frame: pd.DataFrame) -> str:
    payload = frame.to_csv(index=False, lineterminator="\n").encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _canonical_sha256(value: Any) -> str:
    payload = json.dumps(
        _jsonable(value),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _utc_text(value: Any) -> str:
    text = _text(value)
    if not text:
        raise ValueError("vendor intake receipt timestamp is required")
    parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("vendor intake receipt timestamp must be timezone-aware")
    return parsed.astimezone(timezone.utc).isoformat()


def _read_json(path: Path, label: str) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"{label} is unreadable") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"{label} must be a JSON object")
    return payload


def _read_csv(path: Path, label: str) -> pd.DataFrame:
    try:
        return pd.read_csv(path)
    except (OSError, pd.errors.ParserError, pd.errors.EmptyDataError) as exc:
        raise ValueError(f"{label} is unreadable") from exc


def _single_row(frame: pd.DataFrame, label: str) -> pd.Series:
    if len(frame) != 1:
        raise ValueError(f"{label} must contain exactly one row")
    return frame.iloc[0]


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _dataframe_records_equal(actual: pd.DataFrame, expected: pd.DataFrame) -> bool:
    if list(actual.columns) != list(expected.columns) or len(actual) != len(expected):
        return False
    for actual_row, expected_row in zip(
        actual.itertuples(index=False, name=None),
        expected.itertuples(index=False, name=None),
    ):
        for actual_value, expected_value in zip(actual_row, expected_row):
            actual_missing = _artifact_value_missing(actual_value)
            expected_missing = _artifact_value_missing(expected_value)
            if actual_missing or expected_missing:
                if actual_missing != expected_missing:
                    return False
                continue
            if isinstance(actual_value, Real) and isinstance(expected_value, Real):
                if not math.isclose(
                    float(actual_value),
                    float(expected_value),
                    rel_tol=1e-12,
                    abs_tol=1e-12,
                ):
                    return False
            elif str(actual_value) != str(expected_value):
                return False
    return True


def _artifact_value_missing(value: Any) -> bool:
    if value is None or (isinstance(value, str) and value.strip().lower() in {"", "nan"}):
        return True
    try:
        return bool(pd.isna(value))
    except (TypeError, ValueError):
        return False


def _jsonable(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    if hasattr(value, "item"):
        try:
            return value.item()
        except (AttributeError, ValueError):
            pass
    return value


def _column_profiles(sample: pd.DataFrame, source_columns: list[str]) -> pd.DataFrame:
    rows = []
    for column in source_columns:
        values = sample[column]
        non_null = values.dropna()
        non_null_count = int(len(non_null))
        rows.append(
            {
                "source_column": column,
                "normalized_key": _key(column),
                "dtype": str(values.dtype),
                "sampled_rows": int(len(values)),
                "non_null_rows": non_null_count,
                "non_null_rate": _rate(non_null_count, len(values)),
                "numeric_parse_rate": _parse_rate(non_null, kind="numeric"),
                "datetime_parse_rate": _parse_rate(non_null, kind="datetime"),
                "example_values": _examples(non_null),
            }
        )
    return pd.DataFrame(rows)


def _mapping_candidates(source_columns: list[str], kind: str, adapter: str) -> pd.DataFrame:
    canonical_kind, attr = _schema_kind(kind)
    spec = get_adapter(adapter)
    normalized_columns = [str(column) for column in getattr(spec, attr).keys()]
    source_lookup = _key_lookup(source_columns)
    rows = []
    for normalized_column in normalized_columns:
        suggestion = _suggest_source(normalized_column, source_lookup)
        source_column = suggestion["source_column"]
        confidence = suggestion["confidence"]
        mapped = bool(source_column)
        rows.append(
            {
                "adapter": spec.name,
                "kind": canonical_kind,
                "adapter_schema_status": adapter_schema_status(spec.name),
                "normalized_column": normalized_column,
                "source_column": source_column,
                "default_value": "",
                "required": True,
                "transform": suggestion["transform"],
                "confidence": confidence,
                "status": "mapped" if mapped else "unmapped_required",
                "notes": _mapping_note(mapped, confidence),
            }
        )
    return pd.DataFrame(rows)


def _kind_scores(candidates: pd.DataFrame, config: VendorCsvIntakeConfig) -> pd.DataFrame:
    rows = []
    for kind, group in candidates.groupby("kind", sort=False):
        required = int(group["required"].astype(bool).sum())
        mapped_mask = group["source_column"].astype(str) != ""
        mapped = int(mapped_mask.sum())
        exact = int((group["confidence"].astype(str) == "exact").sum())
        alias = int((group["confidence"].astype(str) == "alias").sum())
        coverage = _rate(mapped, required)
        rows.append(
            {
                "adapter": config.adapter,
                "kind": kind,
                "required_columns": required,
                "mapped_columns": mapped,
                "exact_columns": exact,
                "alias_columns": alias,
                "unmapped_required_columns": required - mapped,
                "mapping_coverage": coverage,
                "ready": bool(required > 0 and coverage + 1e-12 >= config.min_mapping_coverage),
            }
        )
    scores = pd.DataFrame(rows)
    if scores.empty:
        return scores
    scores = scores.sort_values(
        ["ready", "mapping_coverage", "mapped_columns", "exact_columns", "alias_columns", "kind"],
        ascending=[False, False, False, False, False, True],
        kind="mergesort",
    )
    return scores.reset_index(drop=True)


def _draft_for_kind(candidates: pd.DataFrame, best_kind: str) -> pd.DataFrame:
    frame = candidates.loc[candidates["kind"].astype(str) == best_kind].copy()
    return frame[
        [
            "normalized_column",
            "source_column",
            "default_value",
            "required",
            "transform",
            "confidence",
            "status",
            "notes",
        ]
    ].reset_index(drop=True)


def _summary(
    *,
    columns: pd.DataFrame,
    kind_scores: pd.DataFrame,
    mapping_draft: pd.DataFrame,
    sample: pd.DataFrame,
    source_path: str,
    source_profile: dict[str, Any],
    config: VendorCsvIntakeConfig,
) -> pd.DataFrame:
    best = kind_scores.iloc[0]
    unmapped = int(best["unmapped_required_columns"])
    ambiguous_kinds = _top_ambiguous_kinds(kind_scores, config)
    ambiguous = len(ambiguous_kinds) > 1
    ready = bool(best["ready"]) and not ambiguous
    unmapped_columns = _unmapped_normalized_columns(mapping_draft)
    blockers = _summary_blockers(
        ambiguous=ambiguous,
        ambiguous_kinds=ambiguous_kinds,
        mapping_blocked=not bool(best["ready"]),
        unmapped_columns=unmapped_columns,
    )
    primary_blocker = blockers[0] if blockers else {}
    blocked_action_count = int(len(blockers))
    next_gate = "intake-vendor-csv" if blocked_action_count else ""
    return pd.DataFrame(
        [
            {
                "ready": ready,
                "adapter": config.adapter,
                "adapter_schema_status": adapter_schema_status(config.adapter),
                "requested_kind": config.kind,
                "best_kind": str(best["kind"]),
                "source_path": source_path,
                "source_file_sha256": str(source_profile.get("file_sha256", "")),
                "source_file_size_bytes": int(source_profile.get("file_size_bytes", 0) or 0),
                "source_header_sha256": str(source_profile.get("header_sha256", "")),
                "sampled_rows": int(len(sample)),
                "source_columns": int(len(columns)),
                "required_columns": int(best["required_columns"]),
                "mapped_columns": int(best["mapped_columns"]),
                "exact_columns": int(best["exact_columns"]),
                "alias_columns": int(best["alias_columns"]),
                "unmapped_required_columns": unmapped,
                "failed_check_count": int(len(blockers)),
                "failed_check_names": ";".join(str(blocker.get("check", "")) for blocker in blockers),
                "first_failed_reason": str(primary_blocker.get("reason", "")),
                "primary_blocker_check": str(primary_blocker.get("check", "")),
                "primary_blocker_value": str(primary_blocker.get("value", "")),
                "primary_blocker_operator": str(primary_blocker.get("operator", "")),
                "primary_blocker_threshold": str(primary_blocker.get("threshold", "")),
                "primary_blocker_reason": str(primary_blocker.get("reason", "")),
                "ready_action_count": 0,
                "blocked_action_count": blocked_action_count,
                "next_gate": next_gate,
                "next_gate_help_command": _help_command(next_gate),
                "primary_action_status": "blocked" if blocked_action_count else "",
                "mapping_coverage": float(best["mapping_coverage"]),
                "min_mapping_coverage": float(config.min_mapping_coverage),
                "kind_selection": _kind_selection(config, ambiguous),
                "selected_kind_ambiguous": ambiguous,
                "ambiguous_kinds": ";".join(ambiguous_kinds),
                "output_mapping_file": config.output_mapping_file,
                "mapping_draft_sha256": "",
                "recommendation": _recommendation(ready, ambiguous),
                "unmapped_normalized_columns": ";".join(unmapped_columns),
            }
        ]
    )


def _unmapped_normalized_columns(mapping_draft: pd.DataFrame) -> list[str]:
    if mapping_draft.empty or "source_column" not in mapping_draft.columns:
        return []
    frame = mapping_draft.copy()
    missing = frame["source_column"].astype(str) == ""
    return [str(value) for value in frame.loc[missing, "normalized_column"].tolist()]


def _summary_blockers(
    *,
    ambiguous: bool,
    ambiguous_kinds: list[str],
    mapping_blocked: bool,
    unmapped_columns: list[str],
) -> list[dict[str, str]]:
    blockers: list[dict[str, str]] = []
    if ambiguous:
        kinds = ";".join(ambiguous_kinds)
        blockers.append(
            {
                "check": "ambiguous_kind_selection",
                "value": kinds,
                "operator": "unique_kind",
                "threshold": "required",
                "reason": f"auto kind selection is ambiguous: {kinds}",
            }
        )
    if mapping_blocked:
        for column in unmapped_columns:
            blockers.append(
                {
                    "check": f"unmapped_required:{column}",
                    "value": column,
                    "operator": "mapped",
                    "threshold": "source_column",
                    "reason": f"{column} normalized column is not mapped to a source column",
                }
            )
    return blockers


ACTION_QUEUE_COLUMNS = [
    "priority",
    "queue_status",
    "source",
    "component",
    "check",
    "normalized_column",
    "next_gate",
    "next_gate_help_command",
    "reason",
    "recommendation",
]


def _action_queue(summary_row: pd.Series, mapping_draft: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    if _to_bool(summary_row.get("selected_kind_ambiguous", False)):
        rows.append(
            _action_row(
                source="vendor_intake_summary",
                component="kind_selection",
                check="ambiguous_kind_selection",
                normalized_column="",
                reason=_text(summary_row.get("primary_blocker_reason"))
                or "auto kind selection is ambiguous",
                recommendation="set_vendor_kind_explicitly_before_normalizing",
            )
        )
    if not mapping_draft.empty:
        for item in mapping_draft.to_dict(orient="records"):
            normalized = _text(item.get("normalized_column"))
            status = _text(item.get("status"))
            required = _to_bool(item.get("required", True), default=True)
            source_column = _text(item.get("source_column"))
            default_value = _text(item.get("default_value"))
            if required and status == "unmapped_required" and not source_column and not default_value:
                rows.append(
                    _action_row(
                        source="vendor_mapping_draft",
                        component="mapping",
                        check=f"unmapped_required:{normalized}",
                        normalized_column=normalized,
                        reason=f"{normalized} normalized column is not mapped to a source column",
                        recommendation="complete_vendor_mapping_before_research",
                    )
                )
    ordered_rows = []
    for priority, row in enumerate(rows, start=1):
        item = {column: row.get(column, "") for column in ACTION_QUEUE_COLUMNS}
        item["priority"] = priority
        ordered_rows.append(item)
    return pd.DataFrame(ordered_rows, columns=ACTION_QUEUE_COLUMNS)


def _action_row(
    *,
    source: str,
    component: str,
    check: str,
    normalized_column: str,
    reason: str,
    recommendation: str,
) -> dict[str, str]:
    next_gate = "intake-vendor-csv"
    return {
        "queue_status": "blocked",
        "source": source,
        "component": component,
        "check": check,
        "normalized_column": normalized_column,
        "next_gate": next_gate,
        "next_gate_help_command": _help_command(next_gate),
        "reason": reason,
        "recommendation": recommendation,
    }


def _config(
    summary_row: pd.Series,
    action_queue: pd.DataFrame,
    config: VendorCsvIntakeConfig,
    *,
    receipt: Mapping[str, Any],
) -> dict[str, Any]:
    primary_action = _first_action_record(action_queue)
    return {
        "schema_version": 1,
        "contract_version": CONTRACT_VERSION,
        "intake_receipt_id": _text(receipt.get("intake_receipt_id")),
        "ready": _to_bool(summary_row.get("ready", False)),
        "adapter": config.adapter,
        "requested_kind": config.kind,
        "best_kind": _text(summary_row.get("best_kind")),
        "kind_selection": _text(summary_row.get("kind_selection")),
        "selected_kind_ambiguous": _to_bool(summary_row.get("selected_kind_ambiguous", False)),
        "ambiguous_kinds": _split_items(summary_row.get("ambiguous_kinds")),
        "source": {
            "path": _text(summary_row.get("source_path")),
            "file_sha256": _text(summary_row.get("source_file_sha256")),
            "file_size_bytes": _int(summary_row.get("source_file_size_bytes")),
            "header_sha256": _text(summary_row.get("source_header_sha256")),
            "columns": _int(summary_row.get("source_columns")),
            "sampled_rows": _int(summary_row.get("sampled_rows")),
        },
        "mapping": {
            "draft_file": _text(summary_row.get("output_mapping_file")),
            "draft_sha256": _text(summary_row.get("mapping_draft_sha256")),
            "required_columns": _int(summary_row.get("required_columns")),
            "mapped_columns": _int(summary_row.get("mapped_columns")),
            "unmapped_required_columns": _int(summary_row.get("unmapped_required_columns")),
            "unmapped_normalized_columns": _split_items(summary_row.get("unmapped_normalized_columns")),
            "coverage": _float(summary_row.get("mapping_coverage")),
            "min_coverage": float(config.min_mapping_coverage),
        },
        "failed_check_count": _int(summary_row.get("failed_check_count")),
        "failed_check_names": _split_items(summary_row.get("failed_check_names")),
        "first_failed_reason": _text(summary_row.get("first_failed_reason")),
        "primary_blocker": {
            "check": _text(summary_row.get("primary_blocker_check")),
            "value": _text(summary_row.get("primary_blocker_value")),
            "operator": _text(summary_row.get("primary_blocker_operator")),
            "threshold": _text(summary_row.get("primary_blocker_threshold")),
            "reason": _text(summary_row.get("primary_blocker_reason")),
        },
        "ready_action_count": _int(summary_row.get("ready_action_count")),
        "blocked_action_count": _int(summary_row.get("blocked_action_count")),
        "next_gate": _text(summary_row.get("next_gate")),
        "next_gate_help_command": _text(summary_row.get("next_gate_help_command")),
        "primary_action_status": _text(summary_row.get("primary_action_status")),
        "primary_action": primary_action,
        "next_actions": _action_records(action_queue),
        "ready_actions": _action_records(_actions_with_status(action_queue, "ready")),
        "blocked_actions": _action_records(_actions_with_status(action_queue, "blocked")),
        "recommendation": _text(summary_row.get("recommendation")),
        "settings": _jsonable(asdict(config)),
        "safety": _safety_payload(),
    }


def _runbook_markdown(summary_row: pd.Series, action_queue: pd.DataFrame) -> str:
    ready_label = "yes" if _to_bool(summary_row.get("ready", False)) else "no"
    lines = [
        "# Vendor CSV Intake Runbook",
        "",
        f"- Ready: {ready_label}",
        f"- Intake receipt: {_text(summary_row.get('intake_receipt_id'))}",
        f"- Contract: {_text(summary_row.get('contract_version'))}",
        f"- Adapter: {_text(summary_row.get('adapter'))}",
        f"- Requested kind: {_text(summary_row.get('requested_kind'))}",
        f"- Best kind: {_text(summary_row.get('best_kind'))}",
        f"- Mapping coverage: {_float(summary_row.get('mapping_coverage')):.4f}",
        f"- Recommendation: {_text(summary_row.get('recommendation'))}",
        f"- Blocked actions: {_int(summary_row.get('blocked_action_count'))}",
        f"- Primary next gate: {_code(summary_row.get('next_gate'))}",
        f"- Primary next gate help: {_code(summary_row.get('next_gate_help_command'))}",
        "- Immutable intake evidence: yes",
        "- Authorizes normalization, research, routing, or submission: no",
        "",
        "## Blocked Actions",
        "",
        _action_queue_table(action_queue),
        "",
    ]
    return "\n".join(lines)


def _action_queue_table(action_queue: pd.DataFrame) -> str:
    if action_queue.empty:
        return "No blocked actions."
    rows = [
        "| priority | check | normalized column | next gate | help | reason |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for item in action_queue.to_dict(orient="records"):
        rows.append(
            "| "
            + " | ".join(
                [
                    _text(item.get("priority")),
                    _text(item.get("check")),
                    _text(item.get("normalized_column")),
                    _code(item.get("next_gate")),
                    _code(item.get("next_gate_help_command")),
                    _text(item.get("reason")),
                ]
            )
            + " |"
        )
    return "\n".join(rows)


def _actions_with_status(action_queue: pd.DataFrame, status: str) -> pd.DataFrame:
    if action_queue.empty or "queue_status" not in action_queue.columns:
        return action_queue.iloc[0:0].copy()
    return action_queue.loc[action_queue["queue_status"].astype(str) == status].copy()


def _first_action_record(action_queue: pd.DataFrame) -> dict[str, object]:
    if action_queue.empty:
        return {}
    return _jsonable_record(action_queue.iloc[0].to_dict())


def _action_records(action_queue: pd.DataFrame) -> list[dict[str, object]]:
    if action_queue.empty:
        return []
    return [_jsonable_record(row) for row in action_queue.to_dict(orient="records")]


def _jsonable_record(row: dict[str, object]) -> dict[str, object]:
    record: dict[str, object] = {}
    for key, value in row.items():
        record[str(key)] = _jsonable_value(value)
    return record


def _jsonable_value(value: object) -> object:
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    return value


def _split_items(value: object) -> list[str]:
    text = _text(value)
    if not text:
        return []
    return [item for item in text.split(";") if item]


def _help_command(next_gate: str) -> str:
    gate = _text(next_gate)
    return f"python -m hft_cli {gate} --help" if gate else ""


def _code(value: object) -> str:
    text = _text(value)
    return f"`{text}`" if text else ""


def _top_ambiguous_kinds(kind_scores: pd.DataFrame, config: VendorCsvIntakeConfig) -> list[str]:
    if config.kind.strip().lower().replace("-", "_") != "auto" or kind_scores.empty:
        return []
    top = kind_scores.iloc[0]
    score_columns = [
        "ready",
        "mapping_coverage",
        "mapped_columns",
        "exact_columns",
        "alias_columns",
        "unmapped_required_columns",
    ]
    tied = kind_scores.copy()
    for column in score_columns:
        tied = tied.loc[tied[column] == top[column]]
    return [str(kind) for kind in tied["kind"]]


def _kind_selection(config: VendorCsvIntakeConfig, ambiguous: bool) -> str:
    if config.kind.strip().lower().replace("-", "_") != "auto":
        return "explicit"
    return "ambiguous" if ambiguous else "auto_unique"


def _recommendation(ready: bool, ambiguous: bool) -> str:
    if ambiguous:
        return "set_vendor_kind_explicitly_before_normalizing"
    return "review_mapping_then_normalize" if ready else "complete_vendor_mapping_before_research"


def _source_profile(
    sample: pd.DataFrame,
    source_columns: list[str],
    sample_path: str | Path | None,
) -> dict[str, Any]:
    profile: dict[str, Any] = {
        "source_path": str(sample_path or ""),
        "sampled_rows": int(len(sample)),
        "source_columns": int(len(source_columns)),
        "header_columns": list(source_columns),
        "header_sha256": _header_sha256(source_columns),
    }
    if sample_path is not None:
        path = Path(sample_path)
        if path.exists() and path.is_file():
            profile["file_size_bytes"] = int(path.stat().st_size)
            profile["file_sha256"] = file_sha256(path)
    return profile


def _with_mapping_profile(
    source_profile: dict[str, Any],
    mapping_path: Path,
    *,
    mapping_sha256: str,
) -> dict[str, Any]:
    profile = dict(source_profile)
    profile["mapping_draft_path"] = str(mapping_path)
    profile["mapping_draft_sha256"] = mapping_sha256
    return profile


def _header_sha256(source_columns: list[str]) -> str:
    payload = json.dumps(source_columns, ensure_ascii=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _candidate_kinds(kind: str) -> list[str]:
    key = kind.strip().lower().replace("-", "_")
    if key == "auto":
        return list(AUTO_KINDS)
    canonical, _ = _schema_kind(key)
    return [canonical]


def _schema_kind(kind: str) -> tuple[str, str]:
    key = kind.strip().lower().replace("-", "_")
    try:
        return SCHEMA_KIND_ATTRS[key]
    except KeyError as exc:
        raise ValueError(f"unknown vendor CSV kind {kind!r}; known kinds: auto or {sorted(SCHEMA_KIND_ATTRS)}") from exc


def _suggest_source(normalized_column: str, source_lookup: dict[str, str]) -> dict[str, str]:
    target_key = _key(normalized_column)
    exact = source_lookup.get(target_key, "")
    if exact:
        return {
            "source_column": exact,
            "transform": _transform_for_target(normalized_column, exact),
            "confidence": "exact",
        }
    for alias in _aliases(normalized_column):
        source = source_lookup.get(_key(alias), "")
        if source:
            return {
                "source_column": source,
                "transform": _transform_for_target(normalized_column, source),
                "confidence": "alias",
            }
    return {"source_column": "", "transform": "identity", "confidence": "none"}


def _aliases(normalized_column: str) -> tuple[str, ...]:
    aliases = {
        "ts": (
            "timestamp",
            "exchange_ts",
            "exchange_time",
            "exch_ts",
            "exch_time",
            "event_time",
            "time",
            "datetime",
            "date_time",
        ),
        "bid": ("best_bid", "bid_price", "bid_px", "bp", "buy_price", "best_buy_price"),
        "ask": ("best_ask", "ask_price", "ask_px", "ap", "offer", "offer_price", "sell_price", "best_sell_price"),
        "bid_qty": ("bid_size", "bid_quantity", "bid_volume", "buy_qty", "buy_quantity", "best_bid_qty"),
        "ask_qty": ("ask_size", "ask_quantity", "ask_volume", "offer_size", "sell_qty", "best_ask_qty"),
        "last": ("last_price", "last_px", "ltp", "trade_price", "traded_price", "close"),
        "last_qty": ("last_size", "last_quantity", "last_traded_qty", "trade_qty", "traded_qty", "volume"),
        "expiry": ("expiry_date", "expiration", "expiration_date", "maturity"),
        "strike": ("strike_price", "strike_px"),
        "call_bid": ("ce_bid", "call_bid_price", "call_best_bid"),
        "call_ask": ("ce_ask", "call_ask_price", "call_best_ask", "call_offer"),
        "call_bid_qty": ("ce_bid_qty", "ce_bid_size", "call_bid_size", "call_bid_quantity"),
        "call_ask_qty": ("ce_ask_qty", "ce_ask_size", "call_ask_size", "call_ask_quantity"),
        "put_bid": ("pe_bid", "put_bid_price", "put_best_bid"),
        "put_ask": ("pe_ask", "put_ask_price", "put_best_ask", "put_offer"),
        "put_bid_qty": ("pe_bid_qty", "pe_bid_size", "put_bid_size", "put_bid_quantity"),
        "put_ask_qty": ("pe_ask_qty", "pe_ask_size", "put_ask_size", "put_ask_quantity"),
        "client_order_id": ("clordid", "client_id", "clientorderid", "order_tag", "tag", "remarks"),
        "instrument_id": ("symbol", "trading_symbol", "tradingsymbol", "security", "contract", "instrument"),
        "ts_sent_ns": ("order_ts", "order_time", "sent_time", "entry_time", "transact_time"),
        "ts_fill_ns": ("fill_ts", "fill_time", "trade_time", "execution_time", "exec_time"),
        "side": ("buy_sell", "buysell", "transaction_type", "order_side", "action"),
        "qty": ("quantity", "order_qty", "orderquantity", "filled_qty", "fill_qty"),
        "price": ("limit_price", "order_price", "fill_price", "fill_px", "trade_price"),
    }
    return aliases.get(normalized_column, ())


def _transform_for_target(normalized_column: str, source_column: str) -> str:
    if normalized_column in {
        "bid_qty",
        "ask_qty",
        "last_qty",
        "call_bid_qty",
        "call_ask_qty",
        "put_bid_qty",
        "put_ask_qty",
        "qty",
    }:
        return "int"
    if normalized_column in {
        "bid",
        "ask",
        "last",
        "strike",
        "call_bid",
        "call_ask",
        "put_bid",
        "put_ask",
        "price",
    }:
        return "float"
    if normalized_column == "side":
        return "side_signed"
    if normalized_column in {"client_order_id", "instrument_id", "expiry"}:
        return "string"
    if _key(source_column) in {"side", "buysell", "transactiontype", "orderside"}:
        return "side_signed"
    return "identity"


def _mapping_note(mapped: bool, confidence: str) -> str:
    if not mapped:
        return "supply source_column or default_value before normalization"
    if confidence == "alias":
        return "alias suggestion; review vendor semantics before normalizing"
    return "source column found"


def _key_lookup(columns: list[str]) -> dict[str, str]:
    lookup: dict[str, str] = {}
    for column in columns:
        lookup.setdefault(_key(column), column)
    return lookup


def _key(value: object) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value).strip().lower())


def _examples(values: pd.Series) -> str:
    examples = []
    for value in values.astype("string").dropna().head(3):
        text = str(value).replace(";", ",").strip()
        if text:
            examples.append(text[:80])
    return ";".join(examples)


def _parse_rate(values: pd.Series, *, kind: str) -> float:
    if values.empty:
        return 0.0
    if kind == "numeric":
        parsed = pd.to_numeric(values, errors="coerce")
    elif kind == "datetime":
        if not pd.api.types.is_object_dtype(values.dtype) and not pd.api.types.is_string_dtype(values.dtype):
            return 0.0
        parsed = pd.to_datetime(values, errors="coerce")
    else:
        raise ValueError(f"unknown parse-rate kind {kind!r}")
    return float(parsed.notna().mean())


def _rate(numerator: int, denominator: int) -> float:
    return float(numerator / denominator) if denominator else 0.0


def _text(value: object) -> str:
    try:
        if pd.isna(value):
            return ""
    except (TypeError, ValueError):
        pass
    return str(value).strip()


def _int(value: object) -> int:
    try:
        if pd.isna(value):
            return 0
        return int(float(value))
    except (TypeError, ValueError):
        return 0


def _float(value: object) -> float:
    try:
        if pd.isna(value):
            return 0.0
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _to_bool(value: object, *, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    try:
        if pd.isna(value):
            return default
    except (TypeError, ValueError):
        pass
    text = str(value).strip().lower()
    if text in {"true", "1", "yes", "y", "pass", "passed", "ready"}:
        return True
    if text in {"false", "0", "no", "n", "fail", "failed", "not_ready", "blocked"}:
        return False
    return default


def _validate_config(config: VendorCsvIntakeConfig) -> None:
    get_adapter(config.adapter)
    _candidate_kinds(config.kind)
    if config.sample_rows <= 0:
        raise ValueError("sample_rows must be positive")
    if not 0 <= config.min_mapping_coverage <= 1:
        raise ValueError("min_mapping_coverage must be between 0 and 1")
    if not config.output_mapping_file:
        raise ValueError("output_mapping_file is required")
    mapping_path = Path(config.output_mapping_file)
    reserved = {name.lower() for name in (*STATIC_ARTIFACTS, MANIFEST_NAME)}
    if (
        mapping_path.is_absolute()
        or len(mapping_path.parts) != 1
        or mapping_path.name in {"", ".", ".."}
    ):
        raise ValueError("output_mapping_file must be a filename within the intake output")
    if mapping_path.name.lower() in reserved:
        raise ValueError("output_mapping_file conflicts with a vendor intake artifact")
