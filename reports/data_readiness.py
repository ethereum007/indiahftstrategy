from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import asdict, dataclass, fields
from datetime import date
from io import StringIO
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from markets.calendars import MARKET_CALENDAR_POLICY
from reports.market_calendar import (
    MarketCalendarReportVerification,
    verify_market_calendar_report,
)
from reports.manifest import (
    MANIFEST_NAME,
    file_sha256,
    verify_experiment_manifest,
    write_experiment_manifest,
)


SUMMARY_FILES = {
    "market_calendar": "market_calendar_summary.csv",
    "vendor_intake": "vendor_intake_summary.csv",
    "schema_audit": "adapter_schema_summary.csv",
    "mapped_data": "mapped_data_summary.csv",
    "tick_diagnostics": "diagnostic_summary.csv",
    "chain_diagnostics": "diagnostic_summary.csv",
    "market_profile": "market_profile_summary.csv",
    "market_portability": "market_portability_config.json",
    "instrument_metadata": "instrument_metadata_summary.csv",
}
DATA_READINESS_RUN_TYPE = "data_readiness"
DATA_READINESS_ITEMS_FILE = "data_readiness_items.csv"
DATA_READINESS_CHECKS_FILE = "data_readiness_checks.csv"
DATA_READINESS_SUMMARY_FILE = "data_readiness_summary.csv"
DATA_READINESS_ACTION_QUEUE_FILE = "data_readiness_action_queue.csv"
DATA_READINESS_CONFIG_FILE = "data_readiness_config.json"
DATA_READINESS_RUNBOOK_FILE = "data_readiness_runbook.md"
DATA_READINESS_REQUIRED_ARTIFACTS = (
    DATA_READINESS_ITEMS_FILE,
    DATA_READINESS_CHECKS_FILE,
    DATA_READINESS_SUMMARY_FILE,
    DATA_READINESS_ACTION_QUEUE_FILE,
    DATA_READINESS_CONFIG_FILE,
    DATA_READINESS_RUNBOOK_FILE,
)


@dataclass(frozen=True)
class DataReadinessThresholds:
    require_market_calendar: bool = False
    require_vendor_intake: bool = False
    require_schema_audit: bool = False
    require_mapped_data: bool = False
    require_reviewed_mapping_normalization: bool = False
    require_target_application_normalization: bool = False
    require_tick_diagnostics: bool = True
    require_chain_diagnostics: bool = False
    require_contract_expiry_validation: bool = False
    require_contract_lot_validation: bool = False
    require_market_profile: bool = False
    require_explicit_fee_model: bool = False
    require_market_portability: bool = False
    require_instrument_metadata: bool = False
    expected_strategy: str | None = None
    expected_market: str | None = None
    expected_adapter: str | None = None
    expected_vendor_data_kind: str | None = None
    min_tick_rows: int = 1
    min_chain_rows: int = 1
    min_chain_expiries: int = 1
    min_chain_strikes: int = 1
    min_chain_expiry_snapshots: int = 1
    min_chain_snapshots_per_expiry: int = 1
    min_chain_snapshot_strikes: int = 1
    max_null_rows: int = 0
    max_nonfinite_rows: int = 0
    max_nonintegral_rows: int = 0
    max_duplicate_tick_rows: int = 0
    max_integer_overflow_rows: int = 0
    max_nonmonotonic_rows: int = 0
    max_crossed_quote_rows: int = 0
    max_nonpositive_quote_rows: int = 0
    max_nonpositive_depth_rows: int = 0
    max_invalid_trade_rows: int = 0
    max_off_tick_price_rows: int | None = None
    max_non_trading_day_rows: int = 0
    max_out_of_session_rows: int = 0
    max_unparseable_contract_expiry_rows: int = 0
    max_expired_contract_rows: int = 0
    max_duplicate_contract_key_rows: int = 0
    max_conflicting_contract_key_rows: int = 0
    max_invalid_contract_expiry_rows: int = 0
    max_uncovered_contract_expiry_rows: int = 0
    max_invalid_contract_lot_rows: int = 0
    max_uncovered_contract_lot_rows: int = 0
    max_tick_p99_gap_ns: float | None = None
    max_tick_median_spread_ticks: float | None = None
    max_chain_median_spread_ticks: float | None = None
    max_chain_snapshot_p99_gap_ns: float | None = None


@dataclass(frozen=True)
class DataReadinessReport:
    items: pd.DataFrame
    checks: pd.DataFrame
    summary: pd.DataFrame
    output_dir: Path | None = None
    action_queue: pd.DataFrame | None = None

    @property
    def ready(self) -> bool:
        return bool(self.summary.iloc[0]["ready"]) if not self.summary.empty else False


@dataclass(frozen=True)
class DataReadinessReportVerification:
    verified: bool
    ready: bool
    manifest_current: bool
    inputs_current: bool
    artifacts_consistent: bool
    non_authorizing: bool
    output_dir: Path
    manifest_path: Path
    manifest_artifact_count: int = 0
    manifest_artifact_match_count: int = 0
    manifest_input_fingerprint_count: int = 0
    manifest_input_fingerprint_match_count: int = 0
    error: str = ""


def evaluate_data_readiness(
    *,
    market_calendar_summary: pd.DataFrame | None = None,
    vendor_intake_summary: pd.DataFrame | None = None,
    schema_audit_summary: pd.DataFrame | None = None,
    mapped_data_summary: pd.DataFrame | None = None,
    tick_diagnostic_summary: pd.DataFrame | None = None,
    chain_diagnostic_summary: pd.DataFrame | None = None,
    market_profile_summary: pd.DataFrame | None = None,
    market_portability_config: dict[str, Any] | None = None,
    instrument_metadata_summary: pd.DataFrame | None = None,
    thresholds: DataReadinessThresholds | None = None,
) -> DataReadinessReport:
    thresholds = thresholds or DataReadinessThresholds()
    _validate_thresholds(thresholds)
    portability_config = _optional_config(market_portability_config)
    summaries = {
        "market_calendar": _optional_frame(market_calendar_summary),
        "vendor_intake": _optional_frame(vendor_intake_summary),
        "schema_audit": _optional_frame(schema_audit_summary),
        "mapped_data": _optional_frame(mapped_data_summary),
        "tick_diagnostics": _optional_frame(tick_diagnostic_summary),
        "chain_diagnostics": _optional_frame(chain_diagnostic_summary),
        "market_profile": _optional_frame(market_profile_summary),
        "market_portability": _market_portability_frame(portability_config, thresholds),
        "instrument_metadata": _optional_frame(instrument_metadata_summary),
    }
    items = _items(summaries, thresholds)
    checks = _checks(summaries, items, thresholds)
    action_queue = _action_queue(checks, items)
    summary = _summary(items, checks, thresholds, action_queue)
    return DataReadinessReport(items=items, checks=checks, summary=summary, action_queue=action_queue)


def write_data_readiness_report(
    *,
    output_dir: str | Path,
    market_calendar_dir: str | Path | None = None,
    vendor_intake_dir: str | Path | None = None,
    schema_audit_dir: str | Path | None = None,
    mapped_data_dir: str | Path | None = None,
    tick_diagnostics_dir: str | Path | None = None,
    chain_diagnostics_dir: str | Path | None = None,
    market_profile_dir: str | Path | None = None,
    market_portability_dir: str | Path | None = None,
    instrument_metadata_dir: str | Path | None = None,
    thresholds: DataReadinessThresholds | None = None,
) -> DataReadinessReport:
    thresholds = thresholds or DataReadinessThresholds()
    _validate_thresholds(thresholds)
    source_paths = {
        "market_calendar": market_calendar_dir,
        "vendor_intake": vendor_intake_dir,
        "schema_audit": schema_audit_dir,
        "mapped_data": mapped_data_dir,
        "tick_diagnostics": tick_diagnostics_dir,
        "chain_diagnostics": chain_diagnostics_dir,
        "market_profile": market_profile_dir,
        "market_portability": market_portability_dir,
        "instrument_metadata": instrument_metadata_dir,
    }
    report, calendar_verification = _build_data_readiness_from_paths(
        source_paths,
        thresholds=thresholds,
    )
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    report.items.to_csv(out / DATA_READINESS_ITEMS_FILE, index=False)
    report.checks.to_csv(out / DATA_READINESS_CHECKS_FILE, index=False)
    report.summary.to_csv(out / DATA_READINESS_SUMMARY_FILE, index=False)
    action_queue = report.action_queue if report.action_queue is not None else _action_queue(report.checks, report.items)
    action_queue.to_csv(out / DATA_READINESS_ACTION_QUEUE_FILE, index=False)
    (out / DATA_READINESS_CONFIG_FILE).write_text(
        json.dumps(
            _config(report.summary.iloc[0], report.items, report.checks, action_queue, thresholds),
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    (out / DATA_READINESS_RUNBOOK_FILE).write_text(
        _runbook_markdown(report.summary.iloc[0], report.items, report.checks, action_queue),
        encoding="utf-8",
    )
    inputs: dict[str, Any] = dict(source_paths)
    if calendar_verification is not None:
        inputs["market_calendar_manifest"] = (
            calendar_verification.manifest_path
        )
        inputs["market_calendar_source"] = (
            calendar_verification.source_path
        )
    write_experiment_manifest(
        out,
        run_type=DATA_READINESS_RUN_TYPE,
        parameters={"thresholds": asdict(thresholds)},
        inputs=inputs,
        extra=_data_readiness_manifest_extra(report),
    )
    return DataReadinessReport(report.items, report.checks, report.summary, out, action_queue)


def verify_data_readiness_report(
    report_dir: str | Path,
) -> DataReadinessReportVerification:
    requested = Path(report_dir)
    root = requested.parent if requested.is_file() else requested
    root = root.resolve()
    manifest_path = root / MANIFEST_NAME
    integrity = verify_experiment_manifest(
        manifest_path,
        expected_run_type=DATA_READINESS_RUN_TYPE,
        required_artifacts=DATA_READINESS_REQUIRED_ARTIFACTS,
        require_input_fingerprints=True,
    )
    inputs_current = False
    artifacts_consistent = False
    non_authorizing = False
    try:
        manifest = _read_json_object(
            manifest_path,
            "data-readiness manifest",
        )
        parameters = _mapping(manifest.get("parameters"))
        thresholds = _data_readiness_thresholds_from_manifest(parameters)
        inputs = _mapping(manifest.get("inputs"))
        source_paths = _data_readiness_source_paths_from_manifest(inputs)
        expected_report, calendar_verification = (
            _build_data_readiness_from_paths(
                source_paths,
                thresholds=thresholds,
            )
        )
        expected_extra = _data_readiness_manifest_extra(expected_report)
        input_contract_current = _data_readiness_input_contract_current(
            inputs,
            source_paths,
            calendar_verification,
        )
        inputs_current = bool(
            input_contract_current
            and integrity.input_fingerprint_count
            == integrity.input_fingerprint_match_count
            and integrity.input_fingerprint_count > 0
        )
        artifacts_consistent = bool(
            _data_readiness_artifacts_consistent(
                root,
                expected_report,
                thresholds,
                manifest,
            )
            and parameters == {"thresholds": asdict(thresholds)}
            and _mapping(manifest.get("extra")) == expected_extra
        )
        non_authorizing = _data_readiness_authority_consistent(
            root,
            _mapping(manifest.get("extra")),
            expected_report.ready,
        )
        verified = bool(
            integrity.passed
            and inputs_current
            and artifacts_consistent
            and non_authorizing
        )
        error = ""
        if not verified:
            error = (
                integrity.error
                or (
                    "data-readiness input contract is invalid"
                    if not inputs_current
                    else ""
                )
                or (
                    "data-readiness artifacts do not reconstruct from inputs"
                    if not artifacts_consistent
                    else ""
                )
                or "data-readiness report widens authority"
            )
        return DataReadinessReportVerification(
            verified=verified,
            ready=bool(verified and expected_report.ready),
            manifest_current=integrity.passed,
            inputs_current=inputs_current,
            artifacts_consistent=artifacts_consistent,
            non_authorizing=non_authorizing,
            output_dir=root,
            manifest_path=manifest_path,
            manifest_artifact_count=integrity.artifact_count,
            manifest_artifact_match_count=integrity.artifact_match_count,
            manifest_input_fingerprint_count=(
                integrity.input_fingerprint_count
            ),
            manifest_input_fingerprint_match_count=(
                integrity.input_fingerprint_match_count
            ),
            error=error,
        )
    except (
        OSError,
        ValueError,
        KeyError,
        TypeError,
        UnicodeDecodeError,
        json.JSONDecodeError,
        pd.errors.EmptyDataError,
        pd.errors.ParserError,
    ) as exc:
        return DataReadinessReportVerification(
            verified=False,
            ready=False,
            manifest_current=integrity.passed,
            inputs_current=inputs_current,
            artifacts_consistent=artifacts_consistent,
            non_authorizing=non_authorizing,
            output_dir=root,
            manifest_path=manifest_path,
            manifest_artifact_count=integrity.artifact_count,
            manifest_artifact_match_count=integrity.artifact_match_count,
            manifest_input_fingerprint_count=(
                integrity.input_fingerprint_count
            ),
            manifest_input_fingerprint_match_count=(
                integrity.input_fingerprint_match_count
            ),
            error=integrity.error or str(exc),
        )


def _build_data_readiness_from_paths(
    source_paths: Mapping[str, str | Path | None],
    *,
    thresholds: DataReadinessThresholds,
) -> tuple[DataReadinessReport, MarketCalendarReportVerification | None]:
    unexpected = set(source_paths) - set(SUMMARY_FILES)
    if unexpected:
        raise ValueError(
            "unsupported data-readiness inputs: "
            + ",".join(sorted(unexpected))
        )
    market_calendar_path = source_paths.get("market_calendar")
    calendar_summary = _read_optional_summary(
        market_calendar_path,
        "market_calendar",
    )
    calendar_verification = (
        verify_market_calendar_report(market_calendar_path)
        if market_calendar_path is not None
        else None
    )
    calendar_summary = _with_market_calendar_verification(
        calendar_summary,
        calendar_verification,
    )
    report = evaluate_data_readiness(
        market_calendar_summary=calendar_summary,
        vendor_intake_summary=_read_optional_summary(
            source_paths.get("vendor_intake"),
            "vendor_intake",
        ),
        schema_audit_summary=_read_optional_summary(
            source_paths.get("schema_audit"),
            "schema_audit",
        ),
        mapped_data_summary=_read_optional_summary(
            source_paths.get("mapped_data"),
            "mapped_data",
        ),
        tick_diagnostic_summary=_read_optional_summary(
            source_paths.get("tick_diagnostics"),
            "tick_diagnostics",
        ),
        chain_diagnostic_summary=_read_optional_summary(
            source_paths.get("chain_diagnostics"),
            "chain_diagnostics",
        ),
        market_profile_summary=_read_optional_summary(
            source_paths.get("market_profile"),
            "market_profile",
        ),
        market_portability_config=_read_optional_market_portability_config(
            source_paths.get("market_portability")
        ),
        instrument_metadata_summary=_read_optional_summary(
            source_paths.get("instrument_metadata"),
            "instrument_metadata",
        ),
        thresholds=thresholds,
    )
    return report, calendar_verification


def _data_readiness_manifest_extra(
    report: DataReadinessReport,
) -> dict[str, object]:
    return {
        "ready": report.ready,
        "non_authorizing": True,
        "authorizes_routing": False,
        "authorizes_submission": False,
    }


def _data_readiness_thresholds_from_manifest(
    parameters: Mapping[str, Any],
) -> DataReadinessThresholds:
    if set(parameters) != {"thresholds"}:
        raise ValueError(
            "data-readiness manifest parameters must contain only thresholds"
        )
    values = _mapping(parameters.get("thresholds"))
    expected_fields = {field.name for field in fields(DataReadinessThresholds)}
    if set(values) != expected_fields:
        raise ValueError(
            "data-readiness manifest threshold contract is incomplete"
        )
    thresholds = DataReadinessThresholds(**dict(values))
    _validate_thresholds(thresholds)
    if dict(values) != asdict(thresholds):
        raise ValueError(
            "data-readiness manifest threshold values are not canonical"
        )
    return thresholds


def _data_readiness_source_paths_from_manifest(
    inputs: Mapping[str, Any],
) -> dict[str, Path]:
    allowed = {
        *SUMMARY_FILES,
        "market_calendar_manifest",
        "market_calendar_source",
    }
    unexpected = set(inputs) - allowed
    if unexpected:
        raise ValueError(
            "data-readiness manifest contains unsupported inputs: "
            + ",".join(sorted(unexpected))
        )
    return {
        component: _manifest_path_input(inputs, component)
        for component in SUMMARY_FILES
        if component in inputs
    }


def _manifest_path_input(
    inputs: Mapping[str, Any],
    name: str,
) -> Path:
    value = _mapping(inputs.get(name))
    if value.get("kind") not in {"file", "directory"} or not value.get(
        "path"
    ):
        raise ValueError(
            f"data-readiness manifest lacks a fingerprinted {name} input"
        )
    return Path(str(value["path"])).resolve()


def _data_readiness_input_contract_current(
    inputs: Mapping[str, Any],
    source_paths: Mapping[str, Path],
    calendar_verification: MarketCalendarReportVerification | None,
) -> bool:
    expected_paths = dict(source_paths)
    if "market_calendar" in source_paths:
        if (
            calendar_verification is None
            or calendar_verification.source_path is None
        ):
            return False
        expected_paths["market_calendar_manifest"] = (
            calendar_verification.manifest_path
        )
        expected_paths["market_calendar_source"] = (
            calendar_verification.source_path
        )
    if set(inputs) != set(expected_paths):
        return False
    return all(
        _manifest_path_fingerprint_matches(
            _mapping(inputs.get(name)),
            Path(path).resolve(),
        )
        for name, path in expected_paths.items()
    )


def _manifest_path_fingerprint_matches(
    fingerprint: Mapping[str, Any],
    path: Path,
) -> bool:
    kind = str(fingerprint.get("kind", ""))
    expected_kind = (
        "file"
        if path.is_file()
        else "directory"
        if path.is_dir()
        else ""
    )
    try:
        return bool(
            expected_kind
            and kind == expected_kind
            and Path(str(fingerprint.get("path", ""))).resolve() == path
        )
    except (OSError, TypeError, ValueError):
        return False


def _data_readiness_artifacts_consistent(
    root: Path,
    expected: DataReadinessReport,
    thresholds: DataReadinessThresholds,
    manifest: Mapping[str, Any],
) -> bool:
    action_queue = (
        expected.action_queue
        if expected.action_queue is not None
        else _action_queue(expected.checks, expected.items)
    )
    expected_config = _config(
        expected.summary.iloc[0],
        expected.items,
        expected.checks,
        action_queue,
        thresholds,
    )
    return bool(
        _data_readiness_manifest_artifacts_exact(manifest)
        and _csv_frame_matches(
            root / DATA_READINESS_ITEMS_FILE,
            expected.items,
        )
        and _csv_frame_matches(
            root / DATA_READINESS_CHECKS_FILE,
            expected.checks,
        )
        and _csv_frame_matches(
            root / DATA_READINESS_SUMMARY_FILE,
            expected.summary,
        )
        and _csv_frame_matches(
            root / DATA_READINESS_ACTION_QUEUE_FILE,
            action_queue,
        )
        and _read_json_object(
            root / DATA_READINESS_CONFIG_FILE,
            "data-readiness config",
        )
        == expected_config
        and (root / DATA_READINESS_RUNBOOK_FILE).read_text(
            encoding="utf-8"
        )
        == _runbook_markdown(
            expected.summary.iloc[0],
            expected.items,
            expected.checks,
            action_queue,
        )
    )


def _data_readiness_manifest_artifacts_exact(
    manifest: Mapping[str, Any],
) -> bool:
    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, list):
        return False
    names = [
        str(item.get("path", "")).replace("\\", "/")
        for item in artifacts
        if isinstance(item, Mapping)
    ]
    return bool(
        len(names) == len(DATA_READINESS_REQUIRED_ARTIFACTS)
        and len(names) == len(artifacts)
        and set(names) == set(DATA_READINESS_REQUIRED_ARTIFACTS)
    )


def _data_readiness_authority_consistent(
    root: Path,
    manifest_extra: Mapping[str, Any],
    ready: bool,
) -> bool:
    summary = _read_csv_frame(
        root / DATA_READINESS_SUMMARY_FILE,
        "data-readiness summary",
    )
    config = _read_json_object(
        root / DATA_READINESS_CONFIG_FILE,
        "data-readiness config",
    )
    if len(summary.index) != 1:
        return False
    row = summary.iloc[0]
    expected = {
        "non_authorizing": True,
        "authorizes_routing": False,
        "authorizes_submission": False,
    }
    return bool(
        _to_bool(row.get("non_authorizing", False))
        and not _to_bool(row.get("authorizes_routing", True))
        and not _to_bool(row.get("authorizes_submission", True))
        and _to_bool(config.get("non_authorizing", False))
        and not _to_bool(config.get("authorizes_routing", True))
        and not _to_bool(config.get("authorizes_submission", True))
        and dict(manifest_extra)
        == {
            "ready": bool(ready),
            **expected,
        }
    )


def _csv_frame_matches(path: Path, expected: pd.DataFrame) -> bool:
    actual = _read_csv_frame(path, path.name)
    expected_roundtrip = pd.read_csv(
        StringIO(expected.to_csv(index=False)),
        keep_default_na=False,
    )
    return bool(
        list(actual.columns) == list(expected_roundtrip.columns)
        and actual.to_dict(orient="records")
        == expected_roundtrip.to_dict(orient="records")
    )


def _read_csv_frame(path: Path, label: str) -> pd.DataFrame:
    try:
        return pd.read_csv(path, keep_default_na=False)
    except (
        OSError,
        UnicodeDecodeError,
        pd.errors.EmptyDataError,
        pd.errors.ParserError,
    ) as exc:
        raise ValueError(f"{label} is unreadable") from exc


def _read_json_object(path: Path, label: str) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"{label} is unreadable") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"{label} must be a JSON object")
    return payload


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _items(summaries: dict[str, pd.DataFrame], thresholds: DataReadinessThresholds) -> pd.DataFrame:
    return pd.DataFrame([_item(name, frame, thresholds) for name, frame in summaries.items()])


def _item(component: str, frame: pd.DataFrame, thresholds: DataReadinessThresholds) -> dict[str, Any]:
    provided = not frame.empty
    required = _component_required(component, thresholds)
    ready = _component_ready(component, frame) if provided else False
    if (
        component == "vendor_intake"
        and provided
        and (
            thresholds.require_reviewed_mapping_normalization
            or thresholds.require_target_application_normalization
        )
    ):
        ready = True
    row = _overall_row(frame) if provided else pd.Series(dtype=object)
    row_count = _number(
        row,
        "rows",
        fallback=_number(row, "output_rows", fallback=_number(row, "sampled_rows", fallback=0.0)),
    )
    failed_checks = _component_failed_checks(component, row)
    return {
        "component": component,
        "required": required,
        "provided": provided,
        "ready": ready,
        "rows": int(row_count),
        "failed_checks": int(failed_checks),
        "source_file": SUMMARY_FILES[component],
        "adapter": _identity(row.get("adapter", "")),
        "market": _identity(row.get("market", "")),
        "kind": _text(row, "best_kind", fallback=_text(row, "kind")),
        "kind_selection": _text(row, "kind_selection"),
        "selected_kind_ambiguous": _to_bool(row.get("selected_kind_ambiguous", False)),
        "ambiguous_kinds": _text(row, "ambiguous_kinds"),
        "source_file_sha256": _text(row, "source_file_sha256"),
        "source_file_size_bytes": _number(row, "source_file_size_bytes"),
        "source_header_sha256": _text(row, "source_header_sha256"),
        "mapping_draft_sha256": _text(row, "mapping_draft_sha256"),
        "mapping_coverage": _number(row, "mapping_coverage"),
        "market_calendar_provided": _to_bool(
            row.get("market_calendar_provided", False)
        ),
        "market_calendar_policy": _text(row, "market_calendar_policy"),
        "market_calendar_id": _text(row, "market_calendar_id"),
        "market_calendar_sha256": _text(row, "market_calendar_sha256"),
        "market_calendar_valid_from": _text(
            row,
            "market_calendar_valid_from",
        ),
        "market_calendar_valid_to": _text(row, "market_calendar_valid_to"),
        "market_calendar_report_verified": _to_bool(
            row.get("market_calendar_report_verified", False)
        ),
        "market_calendar_report_manifest_current": _to_bool(
            row.get("market_calendar_report_manifest_current", False)
        ),
        "market_calendar_report_source_current": _to_bool(
            row.get("market_calendar_report_source_current", False)
        ),
        "market_calendar_report_artifacts_consistent": _to_bool(
            row.get("market_calendar_report_artifacts_consistent", False)
        ),
        "market_calendar_report_non_authorizing": _to_bool(
            row.get("market_calendar_report_non_authorizing", False)
        ),
        "market_calendar_report_verification_error": _text(
            row,
            "market_calendar_report_verification_error",
        ),
        "review_bound": _to_bool(row.get("review_bound", False)),
        "mapping_review_verified": _to_bool(row.get("mapping_review_verified", False)),
        "mapping_review_approved": _to_bool(row.get("mapping_review_approved", False)),
        "mapping_review_id": _text(row, "mapping_review_id"),
        "mapping_review_sha256": _text(row, "mapping_review_sha256"),
        "reviewed_mapping_sha256": _text(row, "reviewed_mapping_sha256"),
        "operator_approved_mapping_required": _to_bool(
            row.get("operator_approved_mapping_required", False)
        ),
        "reviewed_normalization_only": _to_bool(row.get("reviewed_normalization_only", False)),
        "target_application_bound": _to_bool(
            row.get("target_application_bound", False)
        ),
        "mapping_application_verified": _to_bool(
            row.get("mapping_application_verified", False)
        ),
        "mapping_application_ready": _to_bool(
            row.get("mapping_application_ready", False)
        ),
        "mapping_application_id": _text(row, "mapping_application_id"),
        "mapping_application_sha256": _text(row, "mapping_application_sha256"),
        "mapping_scope_review_id": _text(row, "mapping_scope_review_id"),
        "mapping_scope_review_sha256": _text(
            row,
            "mapping_scope_review_sha256",
        ),
        "target_intake_receipt_id": _text(row, "target_intake_receipt_id"),
        "target_application_normalization_only": _to_bool(
            row.get("target_application_normalization_only", False)
        ),
        "normalization_executed": _to_bool(
            row.get("normalization_executed", False)
        ),
        "application_authorizes_normalization": _to_bool(
            row.get("application_authorizes_normalization", False)
        ),
        "authorizes_strategy_research": _to_bool(row.get("authorizes_strategy_research", False)),
        "authorizes_routing": _to_bool(row.get("authorizes_routing", False)),
        "authorizes_submission": _to_bool(row.get("authorizes_submission", False)),
        "recommendation": _component_recommendation(component, provided, ready, required, row),
    }


def _checks(
    summaries: dict[str, pd.DataFrame],
    items: pd.DataFrame,
    thresholds: DataReadinessThresholds,
) -> pd.DataFrame:
    checks = []
    for row in items.itertuples(index=False):
        check_prefix = str(row.component)
        if (
            row.component == "mapped_data"
            and thresholds.require_target_application_normalization
        ):
            check_prefix = "mapped_data_target_application_normalization"
        elif (
            row.component == "mapped_data"
            and thresholds.require_reviewed_mapping_normalization
        ):
            check_prefix = "mapped_data_reviewed_normalization"
        if bool(row.required):
            checks.append(
                _check(
                    f"{check_prefix}_provided",
                    bool(row.provided),
                    "is",
                    True,
                    bool(row.provided),
                    f"{row.component} summary is required but missing",
                )
            )
        if bool(row.required) or bool(row.provided):
            checks.append(
                _check(
                    f"{check_prefix}_ready",
                    bool(row.ready),
                    "is",
                    True,
                    bool(row.ready),
                    f"{row.component} is not ready",
                )
            )

    if not summaries["mapped_data"].empty:
        checks.extend(_mapped_quarantine_checks(summaries["mapped_data"], thresholds))
    if not summaries["tick_diagnostics"].empty:
        checks.extend(_tick_checks(summaries["tick_diagnostics"], thresholds))
    if not summaries["chain_diagnostics"].empty:
        checks.extend(_chain_checks(summaries["chain_diagnostics"], thresholds))
    checks.extend(_market_calendar_checks(summaries, thresholds))
    if not summaries["market_profile"].empty and thresholds.require_explicit_fee_model:
        row = summaries["market_profile"].iloc[0]
        explicit_fee = _to_bool(row.get("explicit_fee_model", False))
        checks.append(
            _check(
                "explicit_fee_model",
                explicit_fee,
                "is",
                True,
                explicit_fee,
                "market profile does not include explicit fee assumptions",
            )
        )
    if (
        not summaries["market_portability"].empty
        and thresholds.expected_strategy is not None
        and thresholds.expected_market is not None
    ):
        row = summaries["market_portability"].iloc[0]
        expected_pair = f"{_identity(thresholds.expected_strategy)}|{_identity(thresholds.expected_market)}"
        pair_ready = _to_bool(row.get("expected_pair_ready", False))
        checks.append(
            _check(
                "market_portability_pair_ready",
                expected_pair,
                "in",
                "ready_pairs",
                pair_ready,
                "expected strategy-market pair is not marked portable or India-ready",
            )
        )
    if not summaries["vendor_intake"].empty:
        row = summaries["vendor_intake"].iloc[0]
        ambiguous = _to_bool(row.get("selected_kind_ambiguous", False))
        checks.append(
            _check(
                "vendor_intake_kind_unambiguous",
                _text(row, "ambiguous_kinds"),
                "is",
                "unambiguous",
                not ambiguous,
                "vendor CSV kind is ambiguous; rerun intake with explicit --kind",
            )
        )
        expected_kind = _vendor_data_kind(thresholds.expected_vendor_data_kind)
        if expected_kind:
            actual_kind = _vendor_data_kind(_text(row, "best_kind", fallback=_text(row, "kind")))
            checks.append(
                _check(
                    "vendor_intake_kind_matches",
                    actual_kind,
                    "==",
                    expected_kind,
                    bool(actual_kind and actual_kind == expected_kind),
                    "vendor intake kind does not match expected market-data kind",
                )
            )
    checks.extend(_data_kind_checks(summaries, thresholds))
    checks.extend(_adapter_checks(summaries, thresholds))
    if thresholds.require_reviewed_mapping_normalization:
        checks.extend(
            _reviewed_mapping_checks(
                summaries["mapped_data"],
                summaries["vendor_intake"],
            )
        )
    if thresholds.require_target_application_normalization:
        checks.extend(
            _target_application_mapping_checks(
                summaries["mapped_data"],
                summaries["vendor_intake"],
            )
        )
    return pd.DataFrame(checks)


def _market_calendar_checks(
    summaries: dict[str, pd.DataFrame],
    thresholds: DataReadinessThresholds,
) -> list[dict[str, Any]]:
    calendar_frame = summaries["market_calendar"]
    reference = (
        _overall_row(calendar_frame)
        if not calendar_frame.empty
        else pd.Series(dtype=object)
    )
    reference_available = not reference.empty
    binding_required = bool(thresholds.require_market_calendar or reference_available)
    checks: list[dict[str, Any]] = []

    if reference_available:
        calendar_id = _text(reference, "market_calendar_id")
        calendar_sha256 = _text(reference, "market_calendar_sha256")
        valid_from = _text(reference, "market_calendar_valid_from")
        valid_to = _text(reference, "market_calendar_valid_to")
        policy = _text(reference, "market_calendar_policy")
        market = _identity(reference.get("market", ""))
        expected_market = _identity(thresholds.expected_market)
        if "market_calendar_report_verified" in reference.index:
            verification_error = _text(
                reference,
                "market_calendar_report_verification_error",
            )
            verification_reasons = {
                "verified": (
                    "market-calendar report failed semantic verification"
                    + (
                        f": {verification_error}"
                        if verification_error
                        else ""
                    )
                ),
                "manifest_current": (
                    "market-calendar report manifest is missing, stale, or invalid"
                ),
                "source_current": (
                    "market-calendar source fingerprint is stale"
                ),
                "artifacts_consistent": (
                    "market-calendar report artifacts do not reconstruct "
                    "from their source"
                ),
                "non_authorizing": "market-calendar report widens authority",
            }
            for suffix, reason in verification_reasons.items():
                field = f"market_calendar_report_{suffix}"
                value = _to_bool(reference.get(field, False))
                checks.append(
                    _check(
                        field,
                        value,
                        "is",
                        True,
                        value,
                        reason,
                    )
                )
        checks.extend(
            [
                _check(
                    "market_calendar_provenance_bound",
                    _to_bool(reference.get("market_calendar_provided", False)),
                    "is",
                    True,
                    _to_bool(reference.get("market_calendar_provided", False)),
                    "market-calendar report does not retain source provenance",
                ),
                _check(
                    "market_calendar_policy",
                    policy,
                    "==",
                    MARKET_CALENDAR_POLICY,
                    policy == MARKET_CALENDAR_POLICY,
                    "market-calendar report does not use the versioned exchange-calendar policy",
                ),
                _check(
                    "market_calendar_id_present",
                    calendar_id,
                    "nonempty",
                    True,
                    bool(calendar_id),
                    "market-calendar report does not retain a calendar identity",
                ),
                _check(
                    "market_calendar_sha256_present",
                    calendar_sha256,
                    "is_sha256",
                    "64 lowercase hexadecimal characters",
                    _is_sha256(calendar_sha256),
                    "market-calendar report does not retain a valid source fingerprint",
                ),
                _check(
                    "market_calendar_coverage_valid",
                    f"{valid_from}|{valid_to}",
                    "ordered",
                    "YYYY-MM-DD coverage",
                    _valid_date_coverage(valid_from, valid_to),
                    "market-calendar report coverage is missing or invalid",
                ),
            ]
        )
        if expected_market:
            checks.append(
                _check(
                    "market_calendar_market_matches",
                    market,
                    "==",
                    expected_market,
                    bool(market and market == expected_market),
                    "market-calendar report market does not match the expected market",
                )
            )

    for component in ("mapped_data", "tick_diagnostics", "chain_diagnostics"):
        frame = summaries[component]
        if frame.empty:
            continue
        row = _overall_row(frame)
        provided = _to_bool(row.get("market_calendar_provided", False))
        if binding_required:
            checks.append(
                _check(
                    f"{component}_market_calendar_provided",
                    provided,
                    "is",
                    True,
                    provided,
                    f"{component} is not bound to the validated market calendar",
                )
            )
        if not provided:
            continue
        component_policy = _text(row, "market_calendar_policy")
        component_id = _text(row, "market_calendar_id")
        component_sha256 = _text(row, "market_calendar_sha256")
        component_valid_from = _text(row, "market_calendar_valid_from")
        component_valid_to = _text(row, "market_calendar_valid_to")
        checks.extend(
            [
                _check(
                    f"{component}_market_calendar_policy",
                    component_policy,
                    "==",
                    MARKET_CALENDAR_POLICY,
                    component_policy == MARKET_CALENDAR_POLICY,
                    f"{component} does not use the versioned exchange-calendar policy",
                ),
                _check(
                    f"{component}_market_calendar_sha256_present",
                    component_sha256,
                    "is_sha256",
                    "64 lowercase hexadecimal characters",
                    _is_sha256(component_sha256),
                    f"{component} does not retain a valid market-calendar fingerprint",
                ),
                _check(
                    f"{component}_market_calendar_coverage_valid",
                    f"{component_valid_from}|{component_valid_to}",
                    "ordered",
                    "YYYY-MM-DD coverage",
                    _valid_date_coverage(component_valid_from, component_valid_to),
                    f"{component} market-calendar coverage is missing or invalid",
                ),
            ]
        )
        if reference_available:
            checks.extend(
                [
                    _check(
                        f"{component}_market_calendar_id_matches",
                        component_id,
                        "==",
                        _text(reference, "market_calendar_id"),
                        bool(
                            component_id
                            and component_id
                            == _text(reference, "market_calendar_id")
                        ),
                        f"{component} uses a different market-calendar identity",
                    ),
                    _check(
                        f"{component}_market_calendar_sha256_matches",
                        component_sha256,
                        "==",
                        _text(reference, "market_calendar_sha256"),
                        bool(
                            _is_sha256(component_sha256)
                            and component_sha256
                            == _text(reference, "market_calendar_sha256")
                        ),
                        f"{component} uses a different market-calendar source",
                    ),
                    _check(
                        f"{component}_market_calendar_coverage_matches",
                        f"{component_valid_from}|{component_valid_to}",
                        "==",
                        "|".join(
                            [
                                _text(reference, "market_calendar_valid_from"),
                                _text(reference, "market_calendar_valid_to"),
                            ]
                        ),
                        bool(
                            component_valid_from
                            == _text(reference, "market_calendar_valid_from")
                            and component_valid_to
                            == _text(reference, "market_calendar_valid_to")
                        ),
                        f"{component} uses different market-calendar coverage",
                    ),
                ]
            )
    return checks


def _valid_date_coverage(valid_from: str, valid_to: str) -> bool:
    try:
        start = date.fromisoformat(valid_from)
        end = date.fromisoformat(valid_to)
    except (TypeError, ValueError):
        return False
    return start.isoformat() == valid_from and end.isoformat() == valid_to and end >= start


def _reviewed_mapping_checks(
    summary: pd.DataFrame,
    vendor_intake_summary: pd.DataFrame,
) -> list[dict[str, Any]]:
    row = _overall_row(summary)
    checks = [
        _explicit_bool_check(
            row,
            "review_bound",
            expected=True,
            reason="mapped data is not bound to an approved mapping review",
        ),
        _explicit_bool_check(
            row,
            "mapping_review_verified",
            expected=True,
            reason="mapped data does not preserve semantic mapping-review verification",
        ),
        _explicit_bool_check(
            row,
            "mapping_review_approved",
            expected=True,
            reason="mapped data does not preserve operator mapping approval",
        ),
        _explicit_bool_check(
            row,
            "operator_approved_mapping_required",
            expected=True,
            reason="mapped data does not require an operator-approved mapping",
        ),
        _explicit_bool_check(
            row,
            "reviewed_normalization_only",
            expected=True,
            reason="mapped data is not restricted to reviewed normalization",
        ),
        _explicit_bool_check(
            row,
            "authorizes_strategy_research",
            expected=False,
            reason="review-bound normalization must not authorize strategy research",
        ),
        _explicit_bool_check(
            row,
            "authorizes_routing",
            expected=False,
            reason="review-bound normalization must not authorize order routing",
        ),
        _explicit_bool_check(
            row,
            "authorizes_submission",
            expected=False,
            reason="review-bound normalization must not authorize order submission",
        ),
    ]
    review_id = _text(row, "mapping_review_id")
    checks.append(
        _check(
            "mapped_data_mapping_review_id_present",
            review_id,
            "nonempty",
            True,
            bool(review_id),
            "mapped data does not retain a mapping-review identity",
        )
    )
    for field, reason in (
        ("mapping_review_sha256", "mapped data does not retain the mapping-review fingerprint"),
        ("source_file_sha256", "mapped data does not retain the reviewed source fingerprint"),
        ("reviewed_mapping_sha256", "mapped data does not retain the reviewed mapping fingerprint"),
    ):
        value = _text(row, field)
        checks.append(
            _check(
                f"mapped_data_{field}_present",
                value,
                "is_sha256",
                "64 lowercase hexadecimal characters",
                _is_sha256(value),
                reason,
            )
        )
    if not vendor_intake_summary.empty:
        intake_source_sha256 = _text(
            _overall_row(vendor_intake_summary),
            "source_file_sha256",
        )
        mapped_source_sha256 = _text(row, "source_file_sha256")
        checks.append(
            _check(
                "mapped_data_vendor_source_consistency",
                mapped_source_sha256,
                "==",
                intake_source_sha256,
                bool(
                    _is_sha256(mapped_source_sha256)
                    and _is_sha256(intake_source_sha256)
                    and mapped_source_sha256 == intake_source_sha256
                ),
                "vendor intake and review-bound normalization use different source files",
            )
        )
    return checks


def _explicit_bool_check(
    row: pd.Series,
    field: str,
    *,
    expected: bool,
    reason: str,
) -> dict[str, Any]:
    present = field in row.index and not pd.isna(row.get(field))
    valid, actual = _strict_bool_value(row.get(field)) if present else (False, False)
    return _check(
        f"mapped_data_{field}",
        actual if present else "missing",
        "is",
        expected,
        bool(present and valid and actual == expected),
        reason,
    )


def _target_application_mapping_checks(
    summary: pd.DataFrame,
    vendor_intake_summary: pd.DataFrame,
) -> list[dict[str, Any]]:
    row = _overall_row(summary)
    checks = [
        _target_application_bool_check(
            row,
            "target_application_bound",
            expected=True,
            reason="mapped data is not bound to a verified target application",
        ),
        _target_application_bool_check(
            row,
            "mapping_application_verified",
            expected=True,
            reason="mapped data does not preserve mapping-application verification",
        ),
        _target_application_bool_check(
            row,
            "mapping_application_ready",
            expected=True,
            reason="mapped data does not preserve a ready mapping application",
        ),
        _target_application_bool_check(
            row,
            "exact_header_verified",
            expected=True,
            reason="mapped data does not preserve exact ordered-header verification",
        ),
        _target_application_bool_check(
            row,
            "operator_approved_mapping_required",
            expected=True,
            reason="target-applied normalization does not require an approved mapping",
        ),
        _target_application_bool_check(
            row,
            "target_application_normalization_only",
            expected=True,
            reason="mapped data is not restricted to target-applied normalization",
        ),
        _target_application_bool_check(
            row,
            "normalization_executed",
            expected=True,
            reason="target-applied mapped data does not prove normalization execution",
        ),
        _target_application_bool_check(
            row,
            "application_authorizes_normalization",
            expected=False,
            reason="the retained mapping application must remain non-authorizing",
        ),
        _target_application_bool_check(
            row,
            "authorizes_strategy_research",
            expected=False,
            reason="target-applied normalization must not authorize strategy research",
        ),
        _target_application_bool_check(
            row,
            "authorizes_routing",
            expected=False,
            reason="target-applied normalization must not authorize order routing",
        ),
        _target_application_bool_check(
            row,
            "authorizes_submission",
            expected=False,
            reason="target-applied normalization must not authorize order submission",
        ),
        _target_application_bool_check(
            row,
            "authorizes_live_release",
            expected=False,
            reason="target-applied normalization must not authorize live release",
        ),
    ]
    for field, reason in (
        (
            "mapping_application_id",
            "mapped data does not retain a mapping-application identity",
        ),
        (
            "mapping_scope_review_id",
            "mapped data does not retain a mapping-scope-review identity",
        ),
        (
            "target_intake_receipt_id",
            "mapped data does not retain a target-intake receipt identity",
        ),
    ):
        value = _text(row, field)
        checks.append(
            _check(
                f"mapped_data_target_application_{field}_present",
                value,
                "nonempty",
                True,
                bool(value),
                reason,
            )
        )
    for field, reason in (
        (
            "mapping_application_sha256",
            "mapped data does not retain the mapping-application fingerprint",
        ),
        (
            "mapping_scope_review_sha256",
            "mapped data does not retain the mapping-scope-review fingerprint",
        ),
        (
            "source_file_sha256",
            "mapped data does not retain the exact target-source fingerprint",
        ),
        (
            "source_header_sha256",
            "mapped data does not retain the exact ordered-header fingerprint",
        ),
        (
            "reviewed_mapping_sha256",
            "mapped data does not retain the target-applied mapping fingerprint",
        ),
    ):
        value = _text(row, field)
        checks.append(
            _check(
                f"mapped_data_target_application_{field}_present",
                value,
                "is_sha256",
                "64 lowercase hexadecimal characters",
                _is_sha256(value),
                reason,
            )
        )
    if not vendor_intake_summary.empty:
        intake_source_sha256 = _text(
            _overall_row(vendor_intake_summary),
            "source_file_sha256",
        )
        mapped_source_sha256 = _text(row, "source_file_sha256")
        checks.append(
            _check(
                "mapped_data_target_application_vendor_source_consistency",
                mapped_source_sha256,
                "==",
                intake_source_sha256,
                bool(
                    _is_sha256(mapped_source_sha256)
                    and _is_sha256(intake_source_sha256)
                    and mapped_source_sha256 == intake_source_sha256
                ),
                "vendor intake and target-applied normalization use different source files",
            )
        )
    return checks


def _target_application_bool_check(
    row: pd.Series,
    field: str,
    *,
    expected: bool,
    reason: str,
) -> dict[str, Any]:
    present = field in row.index and not pd.isna(row.get(field))
    valid, actual = _strict_bool_value(row.get(field)) if present else (False, False)
    check_field = field.removeprefix("target_application_")
    return _check(
        f"mapped_data_target_application_{check_field}",
        actual if present else "missing",
        "is",
        expected,
        bool(present and valid and actual == expected),
        reason,
    )


def _strict_bool_value(value: object) -> tuple[bool, bool]:
    if isinstance(value, (bool, np.bool_)):
        return True, bool(value)
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "1", "yes", "y"}:
            return True, True
        if normalized in {"false", "0", "no", "n"}:
            return True, False
    if isinstance(value, (int, float, np.integer, np.floating)) and not pd.isna(value):
        if float(value) in {0.0, 1.0}:
            return True, bool(value)
    return False, False


def _is_sha256(value: object) -> bool:
    text = str(value or "").strip()
    return len(text) == 64 and all(char in "0123456789abcdef" for char in text)


def _file_fingerprint_current(path_value: object, sha256_value: object) -> bool:
    path_text = str(path_value or "").strip()
    sha256_text = str(sha256_value or "").strip().lower()
    if not path_text or not _is_sha256(sha256_text):
        return False
    try:
        path = Path(path_text).resolve()
        return bool(path.is_file() and file_sha256(path) == sha256_text)
    except OSError:
        return False


def _data_kind_checks(
    summaries: dict[str, pd.DataFrame],
    thresholds: DataReadinessThresholds,
) -> list[dict[str, Any]]:
    data_components = ["vendor_intake", "schema_audit", "mapped_data"]
    provided = {
        component: _component_kind(component, _overall_row(summaries[component]))
        for component in data_components
        if not summaries[component].empty
    }
    checks: list[dict[str, Any]] = []
    expected_kind = _vendor_data_kind(thresholds.expected_vendor_data_kind)
    if expected_kind:
        for component, kind in provided.items():
            if component == "vendor_intake":
                continue
            checks.append(
                _check(
                    f"{component}_kind_matches",
                    kind,
                    "==",
                    expected_kind,
                    bool(kind and kind == expected_kind),
                    f"{component} kind does not match expected market-data kind",
                )
            )
    if len(provided) > 1:
        unique_kinds = sorted({kind for kind in provided.values() if kind})
        checks.append(
            _check(
                "data_kind_consistency",
                ";".join(unique_kinds),
                "count",
                1,
                len(unique_kinds) == 1,
                "vendor intake, schema audit, and mapped-data summaries use different data kinds",
            )
        )
    return checks


def _adapter_checks(
    summaries: dict[str, pd.DataFrame],
    thresholds: DataReadinessThresholds,
) -> list[dict[str, Any]]:
    adapter_components = ["vendor_intake", "schema_audit", "mapped_data"]
    provided = {
        component: _identity(_overall_row(summaries[component]).get("adapter", ""))
        for component in adapter_components
        if not summaries[component].empty
    }
    checks: list[dict[str, Any]] = []
    expected_adapter = _identity(thresholds.expected_adapter)
    if expected_adapter:
        for component, adapter in provided.items():
            checks.append(
                _check(
                    f"{component}_adapter_matches",
                    adapter,
                    "==",
                    expected_adapter,
                    bool(adapter and adapter == expected_adapter),
                    f"{component} adapter does not match expected adapter",
                )
            )
    if len(provided) > 1:
        unique_adapters = sorted({adapter for adapter in provided.values() if adapter})
        checks.append(
            _check(
                "data_adapter_consistency",
                ";".join(unique_adapters),
                "count",
                1,
                len(unique_adapters) == 1,
                "vendor intake, schema audit, and mapped-data summaries use different adapters",
            )
        )
    return checks


def _tick_checks(summary: pd.DataFrame, thresholds: DataReadinessThresholds) -> list[dict[str, Any]]:
    row = summary.iloc[0]
    checks = [
        _threshold_check("tick_rows", _number(row, "rows"), ">=", thresholds.min_tick_rows),
        _threshold_check("tick_nonmonotonic_rows", _number(row, "nonmonotonic_rows"), "<=", thresholds.max_nonmonotonic_rows),
        _threshold_check("tick_crossed_quote_rows", _number(row, "crossed_quote_rows"), "<=", thresholds.max_crossed_quote_rows),
        _threshold_check(
            "tick_nonpositive_quote_rows",
            _number(row, "nonpositive_quote_rows"),
            "<=",
            thresholds.max_nonpositive_quote_rows,
        ),
        _threshold_check(
            "tick_nonpositive_depth_rows",
            _number(row, "nonpositive_depth_rows"),
            "<=",
            thresholds.max_nonpositive_depth_rows,
        ),
        _threshold_check(
            "tick_invalid_trade_rows",
            _number(row, "invalid_trade_rows"),
            "<=",
            thresholds.max_invalid_trade_rows,
        ),
        _threshold_check(
            "tick_non_trading_day_rows",
            _number(row, "non_trading_day_rows", fallback=0.0),
            "<=",
            thresholds.max_non_trading_day_rows,
        ),
        _threshold_check("tick_out_of_session_rows", _number(row, "out_of_session_rows"), "<=", thresholds.max_out_of_session_rows),
    ]
    if thresholds.max_off_tick_price_rows is not None:
        price_grid_enabled = _to_bool(
            row.get("price_grid_validation_enabled", False)
        )
        checks.extend(
            [
                _check(
                    "tick_price_grid_validation_enabled",
                    price_grid_enabled,
                    "is",
                    True,
                    price_grid_enabled,
                    "tick diagnostics did not validate the declared price grid",
                ),
                _threshold_check(
                    "tick_off_tick_price_rows",
                    _number(row, "off_tick_price_rows"),
                    "<=",
                    thresholds.max_off_tick_price_rows,
                ),
            ]
        )
    if thresholds.max_tick_p99_gap_ns is not None:
        checks.append(_threshold_check("tick_p99_gap_ns", _number(row, "p99_gap_ns"), "<=", thresholds.max_tick_p99_gap_ns))
    if thresholds.max_tick_median_spread_ticks is not None:
        checks.append(
            _threshold_check(
                "tick_median_spread_ticks",
                _number(row, "median_spread_ticks"),
                "<=",
                thresholds.max_tick_median_spread_ticks,
            )
        )
    return checks


def _chain_checks(summary: pd.DataFrame, thresholds: DataReadinessThresholds) -> list[dict[str, Any]]:
    row = _overall_row(summary)
    checks = [
        _threshold_check("chain_rows", _number(row, "rows"), ">=", thresholds.min_chain_rows),
        _threshold_check("chain_expiries", _number(row, "expiries"), ">=", thresholds.min_chain_expiries),
        _threshold_check("chain_strikes", _number(row, "strikes"), ">=", thresholds.min_chain_strikes),
        _threshold_check(
            "chain_expiry_snapshots",
            _number(row, "expiry_snapshots", fallback=0.0),
            ">=",
            thresholds.min_chain_expiry_snapshots,
        ),
        _threshold_check(
            "chain_snapshots_per_expiry",
            _number(row, "min_snapshots_per_expiry", fallback=0.0),
            ">=",
            thresholds.min_chain_snapshots_per_expiry,
        ),
        _threshold_check(
            "chain_snapshot_strikes",
            _number(row, "min_snapshot_strikes", fallback=0.0),
            ">=",
            thresholds.min_chain_snapshot_strikes,
        ),
        _threshold_check(
            "chain_nonmonotonic_rows",
            _number(row, "nonmonotonic_rows", fallback=0.0),
            "<=",
            thresholds.max_nonmonotonic_rows,
        ),
        _threshold_check("chain_crossed_quote_rows", _number(row, "crossed_quote_rows"), "<=", thresholds.max_crossed_quote_rows),
        _threshold_check(
            "chain_nonpositive_quote_rows",
            _number(row, "nonpositive_quote_rows"),
            "<=",
            thresholds.max_nonpositive_quote_rows,
        ),
        _threshold_check(
            "chain_nonpositive_depth_rows",
            _number(row, "nonpositive_depth_rows"),
            "<=",
            thresholds.max_nonpositive_depth_rows,
        ),
        _threshold_check(
            "chain_non_trading_day_rows",
            _number(row, "non_trading_day_rows", fallback=0.0),
            "<=",
            thresholds.max_non_trading_day_rows,
        ),
        _threshold_check("chain_out_of_session_rows", _number(row, "out_of_session_rows"), "<=", thresholds.max_out_of_session_rows),
        _threshold_check(
            "chain_unparseable_contract_expiry_rows",
            _number(
                row,
                "unparseable_contract_expiry_rows",
                fallback=0.0,
            ),
            "<=",
            thresholds.max_unparseable_contract_expiry_rows,
        ),
        _threshold_check(
            "chain_expired_contract_rows",
            _number(row, "expired_contract_rows", fallback=0.0),
            "<=",
            thresholds.max_expired_contract_rows,
        ),
        _threshold_check(
            "chain_duplicate_contract_key_rows",
            _number(
                row,
                "duplicate_contract_key_rows",
                fallback=0.0,
            ),
            "<=",
            thresholds.max_duplicate_contract_key_rows,
        ),
        _threshold_check(
            "chain_conflicting_contract_key_rows",
            _number(
                row,
                "conflicting_contract_key_rows",
                fallback=0.0,
            ),
            "<=",
            thresholds.max_conflicting_contract_key_rows,
        ),
    ]
    if thresholds.max_off_tick_price_rows is not None:
        price_grid_enabled = _to_bool(
            row.get("price_grid_validation_enabled", False)
        )
        checks.extend(
            [
                _check(
                    "chain_price_grid_validation_enabled",
                    price_grid_enabled,
                    "is",
                    True,
                    price_grid_enabled,
                    "chain diagnostics did not validate the declared price grid",
                ),
                _threshold_check(
                    "chain_off_tick_price_rows",
                    _number(row, "off_tick_price_rows"),
                    "<=",
                    thresholds.max_off_tick_price_rows,
                ),
            ]
        )
    expiry_validation_enabled = _to_bool(
        row.get("contract_expiry_validation_enabled", False)
    )
    if thresholds.require_contract_expiry_validation:
        checks.append(
            _check(
                "chain_contract_expiry_validation_enabled",
                expiry_validation_enabled,
                "is",
                True,
                expiry_validation_enabled,
                "chain diagnostics did not validate exchange contract expiries",
            )
        )
    if thresholds.require_contract_expiry_validation or expiry_validation_enabled:
        rule_id = _text(row, "contract_expiry_rule_id")
        rule_sha256 = _text(row, "contract_expiry_rule_sha256")
        authority_sha256 = _text(
            row,
            "contract_expiry_authority_source_sha256",
        )
        rule_path = _text(row, "contract_expiry_rule_path")
        authority_path = _text(
            row,
            "contract_expiry_authority_source_path",
        )
        checks.extend(
            [
                _check(
                    "chain_contract_expiry_rule_id_present",
                    rule_id,
                    "nonempty",
                    True,
                    bool(rule_id),
                    "chain diagnostics did not retain an expiry-rule identity",
                ),
                _check(
                    "chain_contract_expiry_rule_sha256_present",
                    rule_sha256,
                    "is_sha256",
                    "64 lowercase hexadecimal characters",
                    _is_sha256(rule_sha256),
                    "chain diagnostics did not retain the expiry-rule fingerprint",
                ),
                _check(
                    "chain_contract_expiry_authority_sha256_present",
                    authority_sha256,
                    "is_sha256",
                    "64 lowercase hexadecimal characters",
                    _is_sha256(authority_sha256),
                    "chain diagnostics did not retain the NSE circular fingerprint",
                ),
                _check(
                    "chain_contract_expiry_rule_current",
                    rule_path,
                    "sha256_matches",
                    rule_sha256,
                    _file_fingerprint_current(rule_path, rule_sha256),
                    "chain diagnostics expiry-rule source is missing or stale",
                ),
                _check(
                    "chain_contract_expiry_authority_current",
                    authority_path,
                    "sha256_matches",
                    authority_sha256,
                    _file_fingerprint_current(
                        authority_path,
                        authority_sha256,
                    ),
                    "chain diagnostics NSE circular source is missing or stale",
                ),
                _threshold_check(
                    "chain_invalid_contract_expiry_rows",
                    _number(row, "invalid_contract_expiry_rows"),
                    "<=",
                    thresholds.max_invalid_contract_expiry_rows,
                ),
                _threshold_check(
                    "chain_uncovered_contract_expiry_rows",
                    _number(row, "uncovered_contract_expiry_rows"),
                    "<=",
                    thresholds.max_uncovered_contract_expiry_rows,
                ),
            ]
        )
    lot_validation_enabled = _to_bool(
        row.get("contract_lot_validation_enabled", False)
    )
    if thresholds.require_contract_lot_validation:
        checks.append(
            _check(
                "chain_contract_lot_validation_enabled",
                lot_validation_enabled,
                "is",
                True,
                lot_validation_enabled,
                "chain diagnostics did not validate the declared contract lot size",
            )
        )
    if thresholds.require_contract_lot_validation or lot_validation_enabled:
        underlying = _text(row, "contract_lot_underlying")
        declared_lot_size = _number(row, "contract_lot_size")
        rule_id = _text(row, "contract_lot_rule_id")
        rule_sha256 = _text(row, "contract_lot_rule_sha256")
        authority_sha256 = _text(
            row,
            "contract_lot_authority_source_sha256",
        )
        snapshot_sha256 = _text(
            row,
            "contract_lot_snapshot_sha256",
        )
        rule_path = _text(row, "contract_lot_rule_path")
        authority_path = _text(
            row,
            "contract_lot_authority_source_path",
        )
        snapshot_path = _text(row, "contract_lot_snapshot_path")
        checks.extend(
            [
                _check(
                    "chain_contract_lot_underlying_present",
                    underlying,
                    "nonempty",
                    True,
                    bool(underlying),
                    "chain diagnostics did not retain the declared index underlying",
                ),
                _check(
                    "chain_contract_lot_size_positive",
                    declared_lot_size,
                    ">",
                    0,
                    declared_lot_size > 0,
                    "chain diagnostics did not retain a positive declared lot size",
                ),
                _check(
                    "chain_contract_lot_rule_id_present",
                    rule_id,
                    "nonempty",
                    True,
                    bool(rule_id),
                    "chain diagnostics did not retain a contract-lot rule identity",
                ),
                _check(
                    "chain_contract_lot_rule_sha256_present",
                    rule_sha256,
                    "is_sha256",
                    "64 lowercase hexadecimal characters",
                    _is_sha256(rule_sha256),
                    "chain diagnostics did not retain the contract-lot rule fingerprint",
                ),
                _check(
                    "chain_contract_lot_authority_sha256_present",
                    authority_sha256,
                    "is_sha256",
                    "64 lowercase hexadecimal characters",
                    _is_sha256(authority_sha256),
                    "chain diagnostics did not retain the NSE lot-size circular fingerprint",
                ),
                _check(
                    "chain_contract_lot_snapshot_sha256_present",
                    snapshot_sha256,
                    "is_sha256",
                    "64 lowercase hexadecimal characters",
                    _is_sha256(snapshot_sha256),
                    "chain diagnostics did not retain the NSE permitted-lot snapshot fingerprint",
                ),
                _check(
                    "chain_contract_lot_rule_current",
                    rule_path,
                    "sha256_matches",
                    rule_sha256,
                    _file_fingerprint_current(rule_path, rule_sha256),
                    "chain diagnostics contract-lot rule source is missing or stale",
                ),
                _check(
                    "chain_contract_lot_authority_current",
                    authority_path,
                    "sha256_matches",
                    authority_sha256,
                    _file_fingerprint_current(
                        authority_path,
                        authority_sha256,
                    ),
                    "chain diagnostics NSE lot-size circular is missing or stale",
                ),
                _check(
                    "chain_contract_lot_snapshot_current",
                    snapshot_path,
                    "sha256_matches",
                    snapshot_sha256,
                    _file_fingerprint_current(
                        snapshot_path,
                        snapshot_sha256,
                    ),
                    "chain diagnostics NSE permitted-lot snapshot is missing or stale",
                ),
                _threshold_check(
                    "chain_invalid_contract_lot_rows",
                    _number(row, "invalid_contract_lot_rows"),
                    "<=",
                    thresholds.max_invalid_contract_lot_rows,
                ),
                _threshold_check(
                    "chain_uncovered_contract_lot_rows",
                    _number(row, "uncovered_contract_lot_rows"),
                    "<=",
                    thresholds.max_uncovered_contract_lot_rows,
                ),
            ]
        )
    if thresholds.max_chain_median_spread_ticks is not None:
        expiry_rows = summary.loc[summary.get("scope", "") == "expiry"] if "scope" in summary.columns else pd.DataFrame()
        call_spread = _max_number(expiry_rows, "median_call_spread_ticks")
        put_spread = _max_number(expiry_rows, "median_put_spread_ticks")
        checks.append(
            _threshold_check(
                "chain_median_spread_ticks",
                max(call_spread, put_spread),
                "<=",
                thresholds.max_chain_median_spread_ticks,
            )
        )
    if thresholds.max_chain_snapshot_p99_gap_ns is not None:
        checks.append(
            _threshold_check(
                "chain_snapshot_p99_gap_ns",
                _number(row, "p99_snapshot_gap_ns", fallback=0.0),
                "<=",
                thresholds.max_chain_snapshot_p99_gap_ns,
            )
        )
    return checks


def _mapped_quarantine_checks(
    summary: pd.DataFrame,
    thresholds: DataReadinessThresholds,
) -> list[dict[str, Any]]:
    quarantine_fields = {
        "dropped_null_rows",
        "dropped_nonfinite_rows",
        "dropped_nonintegral_rows",
        "dropped_duplicate_rows",
        "dropped_integer_overflow_rows",
        "dropped_crossed_quote_rows",
        "dropped_nonpositive_quote_rows",
        "dropped_nonmonotonic_rows",
        "dropped_negative_depth_rows",
        "dropped_invalid_trade_rows",
        "dropped_non_trading_day_rows",
        "dropped_out_of_session_rows",
    }
    if not quarantine_fields.intersection(summary.columns):
        return []
    row = _overall_row(summary)
    checks = [
        _threshold_check(
            "mapped_data_dropped_null_rows",
            _number(row, "dropped_null_rows"),
            "<=",
            thresholds.max_null_rows,
        ),
        _threshold_check(
            "mapped_data_dropped_nonfinite_rows",
            _number(row, "dropped_nonfinite_rows"),
            "<=",
            thresholds.max_nonfinite_rows,
        ),
        _threshold_check(
            "mapped_data_dropped_nonintegral_rows",
            _number(row, "dropped_nonintegral_rows"),
            "<=",
            thresholds.max_nonintegral_rows,
        ),
        _threshold_check(
            "mapped_data_dropped_integer_overflow_rows",
            _number(row, "dropped_integer_overflow_rows"),
            "<=",
            thresholds.max_integer_overflow_rows,
        ),
        _threshold_check(
            "mapped_data_dropped_crossed_quote_rows",
            _number(row, "dropped_crossed_quote_rows"),
            "<=",
            thresholds.max_crossed_quote_rows,
        ),
        _threshold_check(
            "mapped_data_dropped_nonpositive_quote_rows",
            _number(row, "dropped_nonpositive_quote_rows"),
            "<=",
            thresholds.max_nonpositive_quote_rows,
        ),
        _threshold_check(
            "mapped_data_dropped_non_trading_day_rows",
            _number(row, "dropped_non_trading_day_rows"),
            "<=",
            thresholds.max_non_trading_day_rows,
        ),
        _threshold_check(
            "mapped_data_dropped_out_of_session_rows",
            _number(row, "dropped_out_of_session_rows"),
            "<=",
            thresholds.max_out_of_session_rows,
        ),
    ]
    kind = _vendor_data_kind(_text(row, "kind"))
    if kind in {"ticks", "chain"}:
        checks.append(
            _threshold_check(
                "mapped_data_dropped_nonmonotonic_rows",
                _number(row, "dropped_nonmonotonic_rows"),
                "<=",
                thresholds.max_nonmonotonic_rows,
            )
        )
    if kind == "ticks":
        checks.extend(
            [
                _threshold_check(
                    "mapped_data_dropped_duplicate_tick_rows",
                    _number(row, "dropped_duplicate_rows"),
                    "<=",
                    thresholds.max_duplicate_tick_rows,
                ),
                _threshold_check(
                    "mapped_data_dropped_invalid_trade_rows",
                    _number(row, "dropped_invalid_trade_rows"),
                    "<=",
                    thresholds.max_invalid_trade_rows,
                ),
            ]
        )
    if kind in {"ticks", "chain"}:
        checks.append(
            _threshold_check(
                "mapped_data_dropped_negative_depth_rows",
                _number(row, "dropped_negative_depth_rows"),
                "<=",
                thresholds.max_nonpositive_depth_rows,
            )
        )
    return checks


def _summary(
    items: pd.DataFrame,
    checks: pd.DataFrame,
    thresholds: DataReadinessThresholds,
    action_queue: pd.DataFrame,
) -> pd.DataFrame:
    failed_rows = _failed_check_rows(checks)
    failed = int(len(failed_rows)) if not checks.empty else 1
    required = items.loc[items["required"].astype(bool)] if not items.empty else pd.DataFrame()
    ready = failed == 0
    next_gate = _primary_next_gate(action_queue)
    primary_blocker = _first_failed_check(failed_rows)
    return pd.DataFrame(
        [
            {
                "ready": ready,
                "non_authorizing": True,
                "authorizes_routing": False,
                "authorizes_submission": False,
                "components": int(len(items)),
                "required_components": int(len(required)),
                "provided_components": int(items["provided"].astype(bool).sum()) if not items.empty else 0,
                "ready_components": int(items["ready"].astype(bool).sum()) if not items.empty else 0,
                "failed_checks": failed,
                "failed_check_count": failed,
                "failed_check_names": _failed_check_names(failed_rows),
                "first_failed_reason": _check_reason(primary_blocker),
                "primary_blocker_check": _check_name(primary_blocker),
                "primary_blocker_value": _check_value(primary_blocker, "value"),
                "primary_blocker_operator": _check_value(primary_blocker, "operator"),
                "primary_blocker_threshold": _check_value(primary_blocker, "threshold"),
                "primary_blocker_reason": _check_reason(primary_blocker),
                "require_explicit_fee_model": bool(thresholds.require_explicit_fee_model),
                "require_market_calendar": bool(thresholds.require_market_calendar),
                "require_reviewed_mapping_normalization": bool(
                    thresholds.require_reviewed_mapping_normalization
                ),
                "require_target_application_normalization": bool(
                    thresholds.require_target_application_normalization
                ),
                "expected_strategy": _identity(thresholds.expected_strategy),
                "expected_market": _identity(thresholds.expected_market),
                "expected_adapter": _identity(thresholds.expected_adapter),
                "market_calendar_id": _component_text(
                    items,
                    "market_calendar",
                    "market_calendar_id",
                ),
                "market_calendar_sha256": _component_text(
                    items,
                    "market_calendar",
                    "market_calendar_sha256",
                ),
                "market_calendar_valid_from": _component_text(
                    items,
                    "market_calendar",
                    "market_calendar_valid_from",
                ),
                "market_calendar_valid_to": _component_text(
                    items,
                    "market_calendar",
                    "market_calendar_valid_to",
                ),
                "market_calendar_market": _component_text(
                    items,
                    "market_calendar",
                    "market",
                ),
                "market_calendar_report_verified": _component_bool(
                    items,
                    "market_calendar",
                    "market_calendar_report_verified",
                ),
                "market_calendar_report_manifest_current": _component_bool(
                    items,
                    "market_calendar",
                    "market_calendar_report_manifest_current",
                ),
                "market_calendar_report_source_current": _component_bool(
                    items,
                    "market_calendar",
                    "market_calendar_report_source_current",
                ),
                "market_calendar_report_artifacts_consistent": _component_bool(
                    items,
                    "market_calendar",
                    "market_calendar_report_artifacts_consistent",
                ),
                "market_calendar_report_non_authorizing": _component_bool(
                    items,
                    "market_calendar",
                    "market_calendar_report_non_authorizing",
                ),
                "market_calendar_report_verification_error": _component_text(
                    items,
                    "market_calendar",
                    "market_calendar_report_verification_error",
                ),
                "market_calendar_binding_components": _calendar_binding_components(
                    items
                ),
                "market_calendar_binding_count": _calendar_binding_count(items),
                "data_adapters": _joined_component_values(items, "adapter"),
                "data_adapter_count": _component_value_count(items, "adapter"),
                "expected_vendor_data_kind": _vendor_data_kind(thresholds.expected_vendor_data_kind),
                "data_kinds": _joined_component_kinds(items),
                "data_kind_count": _component_kind_count(items),
                "vendor_intake_kind": _component_text(items, "vendor_intake", "kind"),
                "vendor_intake_kind_selection": _component_text(items, "vendor_intake", "kind_selection"),
                "vendor_intake_selected_kind_ambiguous": _component_bool(
                    items,
                    "vendor_intake",
                    "selected_kind_ambiguous",
                ),
                "vendor_intake_ambiguous_kinds": _component_text(items, "vendor_intake", "ambiguous_kinds"),
                "vendor_intake_source_file_sha256": _component_text(items, "vendor_intake", "source_file_sha256"),
                "vendor_intake_source_file_size_bytes": _component_number(
                    items,
                    "vendor_intake",
                    "source_file_size_bytes",
                ),
                "vendor_intake_source_header_sha256": _component_text(items, "vendor_intake", "source_header_sha256"),
                "vendor_intake_mapping_draft_sha256": _component_text(items, "vendor_intake", "mapping_draft_sha256"),
                "vendor_intake_mapping_coverage": _component_number(items, "vendor_intake", "mapping_coverage"),
                "mapped_data_review_bound": _component_bool(items, "mapped_data", "review_bound"),
                "mapped_data_mapping_review_verified": _component_bool(
                    items,
                    "mapped_data",
                    "mapping_review_verified",
                ),
                "mapped_data_mapping_review_approved": _component_bool(
                    items,
                    "mapped_data",
                    "mapping_review_approved",
                ),
                "mapped_data_mapping_review_id": _component_text(items, "mapped_data", "mapping_review_id"),
                "mapped_data_mapping_review_sha256": _component_text(
                    items,
                    "mapped_data",
                    "mapping_review_sha256",
                ),
                "mapped_data_source_file_sha256": _component_text(
                    items,
                    "mapped_data",
                    "source_file_sha256",
                ),
                "mapped_data_reviewed_mapping_sha256": _component_text(
                    items,
                    "mapped_data",
                    "reviewed_mapping_sha256",
                ),
                "mapped_data_target_application_bound": _component_bool(
                    items,
                    "mapped_data",
                    "target_application_bound",
                ),
                "mapped_data_mapping_application_verified": _component_bool(
                    items,
                    "mapped_data",
                    "mapping_application_verified",
                ),
                "mapped_data_mapping_application_ready": _component_bool(
                    items,
                    "mapped_data",
                    "mapping_application_ready",
                ),
                "mapped_data_mapping_application_id": _component_text(
                    items,
                    "mapped_data",
                    "mapping_application_id",
                ),
                "mapped_data_mapping_application_sha256": _component_text(
                    items,
                    "mapped_data",
                    "mapping_application_sha256",
                ),
                "mapped_data_mapping_scope_review_id": _component_text(
                    items,
                    "mapped_data",
                    "mapping_scope_review_id",
                ),
                "mapped_data_mapping_scope_review_sha256": _component_text(
                    items,
                    "mapped_data",
                    "mapping_scope_review_sha256",
                ),
                "mapped_data_target_intake_receipt_id": _component_text(
                    items,
                    "mapped_data",
                    "target_intake_receipt_id",
                ),
                "ready_action_count": 0,
                "blocked_action_count": int(len(action_queue)),
                "next_gate": next_gate,
                "next_gate_help_command": _next_gate_help_command(next_gate),
                "recommendation": "feed_strategy_research" if ready else "fix_data_readiness_gaps",
            }
        ]
    )


def _config(
    summary_row: pd.Series,
    items: pd.DataFrame,
    checks: pd.DataFrame,
    action_queue: pd.DataFrame,
    thresholds: DataReadinessThresholds,
) -> dict[str, Any]:
    ready_actions = _actions_with_status(action_queue, "ready")
    blocked_actions = _actions_with_status(action_queue, "blocked")
    primary_action = _first_action_record(action_queue)
    failed_rows = _failed_check_rows(checks)
    failed_checks = _failed_check_list(failed_rows)
    primary_blocker = _first_failed_check_record(failed_rows)
    return {
        "schema_version": 1,
        "ready": _to_bool(summary_row.get("ready", False)),
        "non_authorizing": True,
        "authorizes_routing": False,
        "authorizes_submission": False,
        "recommendation": _value_text(summary_row.get("recommendation")),
        "thresholds": asdict(thresholds),
        "summary": _jsonable_record(summary_row.to_dict()),
        "component_counts": {
            "components": int(_value_number(summary_row.get("components"))),
            "required": int(_value_number(summary_row.get("required_components"))),
            "provided": int(_value_number(summary_row.get("provided_components"))),
            "ready": int(_value_number(summary_row.get("ready_components"))),
            "failed_checks": int(_value_number(summary_row.get("failed_checks"))),
        },
        "expected_strategy": _value_text(summary_row.get("expected_strategy")),
        "expected_market": _value_text(summary_row.get("expected_market")),
        "expected_adapter": _value_text(summary_row.get("expected_adapter")),
        "expected_vendor_data_kind": _value_text(summary_row.get("expected_vendor_data_kind")),
        "market_calendar": {
            "required": _to_bool(summary_row.get("require_market_calendar", False)),
            "report_verified": _to_bool(
                summary_row.get("market_calendar_report_verified", False)
            ),
            "report_manifest_current": _to_bool(
                summary_row.get(
                    "market_calendar_report_manifest_current",
                    False,
                )
            ),
            "report_source_current": _to_bool(
                summary_row.get(
                    "market_calendar_report_source_current",
                    False,
                )
            ),
            "report_artifacts_consistent": _to_bool(
                summary_row.get(
                    "market_calendar_report_artifacts_consistent",
                    False,
                )
            ),
            "report_non_authorizing": _to_bool(
                summary_row.get(
                    "market_calendar_report_non_authorizing",
                    False,
                )
            ),
            "report_verification_error": _value_text(
                summary_row.get(
                    "market_calendar_report_verification_error",
                )
            ),
            "market": _value_text(summary_row.get("market_calendar_market")),
            "id": _value_text(summary_row.get("market_calendar_id")),
            "sha256": _value_text(summary_row.get("market_calendar_sha256")),
            "valid_from": _value_text(
                summary_row.get("market_calendar_valid_from")
            ),
            "valid_to": _value_text(summary_row.get("market_calendar_valid_to")),
            "binding_components": _value_text(
                summary_row.get("market_calendar_binding_components")
            ).split(";")
            if _value_text(summary_row.get("market_calendar_binding_components"))
            else [],
            "binding_count": int(
                _value_number(summary_row.get("market_calendar_binding_count"))
            ),
        },
        "data_adapters": _value_text(summary_row.get("data_adapters")),
        "data_kinds": _value_text(summary_row.get("data_kinds")),
        "failed_check_count": int(_value_number(summary_row.get("failed_check_count", len(failed_checks)))),
        "failed_checks": failed_checks,
        "first_failed_reason": _value_text(summary_row.get("first_failed_reason")),
        "primary_blocker": primary_blocker,
        "components": _records(items),
        "ready_action_count": int(len(ready_actions)),
        "blocked_action_count": int(len(blocked_actions)),
        "next_gate": _first_action_value(action_queue, "next_gate"),
        "next_gate_help_command": _first_action_value(action_queue, "next_gate_help_command"),
        "primary_action_status": _value_text(primary_action.get("queue_status")),
        "primary_action": primary_action,
        "next_actions": _records(action_queue),
        "ready_actions": _records(ready_actions),
        "blocked_actions": _records(blocked_actions),
    }


def _failed_check_rows(checks: pd.DataFrame) -> pd.DataFrame:
    if checks.empty or "passed" not in checks.columns:
        return checks.iloc[0:0].copy()
    return checks.loc[~checks["passed"].astype(bool)].reset_index(drop=True)


def _failed_check_list(failed_rows: pd.DataFrame) -> list[str]:
    if failed_rows.empty or "check" not in failed_rows.columns:
        return []
    return [_value_text(value) for value in failed_rows["check"].tolist() if _value_text(value)]


def _failed_check_names(failed_rows: pd.DataFrame) -> str:
    return ";".join(_failed_check_list(failed_rows))


def _first_failed_check(failed_rows: pd.DataFrame) -> pd.Series:
    if failed_rows.empty:
        return pd.Series(dtype=object)
    return failed_rows.iloc[0]


def _first_failed_check_record(failed_rows: pd.DataFrame) -> dict[str, object]:
    if failed_rows.empty:
        return {}
    return _jsonable_record(failed_rows.iloc[0].to_dict())


def _check_name(row: pd.Series) -> str:
    return _check_value(row, "check")


def _check_reason(row: pd.Series) -> str:
    return _check_value(row, "reason")


def _check_value(row: pd.Series, column: str) -> str:
    if row.empty:
        return ""
    return _value_text(row.get(column, ""))


def _first_action_record(frame: pd.DataFrame) -> dict[str, Any]:
    if frame.empty:
        return {}
    return _jsonable_record(frame.iloc[0].to_dict())


def _records(frame: pd.DataFrame) -> list[dict[str, Any]]:
    if frame.empty:
        return []
    return [_jsonable_record(row) for row in frame.to_dict(orient="records")]


def _actions_with_status(action_queue: pd.DataFrame, status: str) -> pd.DataFrame:
    if action_queue.empty or "queue_status" not in action_queue.columns:
        return action_queue.iloc[0:0].copy()
    return action_queue.loc[action_queue["queue_status"].astype(str) == status].copy()


def _jsonable_record(row: dict[str, object]) -> dict[str, object]:
    record: dict[str, object] = {}
    for key, value in row.items():
        if isinstance(value, Path):
            record[str(key)] = str(value)
            continue
        try:
            if pd.isna(value):
                record[str(key)] = None
                continue
        except (TypeError, ValueError):
            pass
        if isinstance(value, np.generic):
            record[str(key)] = value.item()
            continue
        record[str(key)] = value
    return record


def _first_action_value(action_queue: pd.DataFrame, column: str) -> str:
    if action_queue.empty or column not in action_queue.columns:
        return ""
    return _value_text(action_queue.iloc[0].get(column))


def _action_queue(checks: pd.DataFrame, items: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    if not checks.empty and "passed" in checks.columns:
        failed = checks.loc[~checks["passed"].astype(bool)].reset_index(drop=True)
        item_recommendations = _item_recommendations(items)
        for priority, row in enumerate(failed.to_dict(orient="records"), start=1):
            check_name = _value_text(row.get("check"))
            component = _action_component(check_name)
            next_gate = _next_gate_for_check(check_name, component)
            rows.append(
                {
                    "priority": priority,
                    "queue_status": "blocked",
                    "check": check_name,
                    "component": component,
                    "next_gate": next_gate,
                    "next_gate_help_command": _next_gate_help_command(next_gate),
                    "actual": _value_text(row.get("value")),
                    "operator": _value_text(row.get("operator")),
                    "expected": _value_text(row.get("threshold")),
                    "reason": _value_text(row.get("reason")),
                    "recommendation": _action_recommendation(
                        check_name,
                        component,
                        item_recommendations.get(component, ""),
                    ),
                }
            )
    return pd.DataFrame(
        rows,
        columns=[
            "priority",
            "queue_status",
            "check",
            "component",
            "next_gate",
            "next_gate_help_command",
            "actual",
            "operator",
            "expected",
            "reason",
            "recommendation",
        ],
    )


def _item_recommendations(items: pd.DataFrame) -> dict[str, str]:
    if items.empty or "component" not in items.columns or "recommendation" not in items.columns:
        return {}
    return {
        _value_text(row.get("component")): _value_text(row.get("recommendation"))
        for row in items.to_dict(orient="records")
    }


def _action_component(check_name: str) -> str:
    if check_name in {"data_kind_consistency", "data_adapter_consistency"}:
        return "vendor_market_data_pipeline"
    if check_name == "explicit_fee_model":
        return "market_profile"
    known_components = [
        "market_calendar",
        "vendor_intake",
        "schema_audit",
        "mapped_data",
        "tick_diagnostics",
        "chain_diagnostics",
        "market_profile",
        "market_portability",
        "instrument_metadata",
    ]
    for component in known_components:
        if check_name == component or check_name.startswith(f"{component}_"):
            return component
    if check_name.startswith("tick_"):
        return "tick_diagnostics"
    if check_name.startswith("chain_"):
        return "chain_diagnostics"
    return "data_readiness"


def _next_gate_for_check(check_name: str, component: str) -> str:
    if check_name in {"data_kind_consistency", "data_adapter_consistency"}:
        return "pipeline-vendor-market-data"
    if check_name == "explicit_fee_model":
        return "market-profile-report"
    if _is_target_application_mapping_check(check_name):
        return "normalize-applied-vendor-mapping"
    if _is_reviewed_mapping_check(check_name):
        return "normalize-reviewed-mapped-data"
    return {
        "vendor_intake": "intake-vendor-csv",
        "market_calendar": "market-calendar-report",
        "schema_audit": "audit-adapter-schema",
        "mapped_data": "normalize-mapped-data",
        "tick_diagnostics": "diagnose-ticks",
        "chain_diagnostics": "diagnose-chain",
        "market_profile": "market-profile-report",
        "market_portability": "market-portability-report",
        "instrument_metadata": "instrument-metadata-report",
    }.get(component, "review-data-readiness")


def _next_gate_help_command(next_gate: str) -> str:
    return f"python -m hft_cli {next_gate} --help" if next_gate else ""


def _primary_next_gate(action_queue: pd.DataFrame) -> str:
    if action_queue.empty:
        return ""
    return _value_text(action_queue.iloc[0].get("next_gate"))


def _action_recommendation(check_name: str, component: str, item_recommendation: str) -> str:
    if _is_target_application_mapping_check(check_name):
        return "normalize_with_verified_target_mapping_application"
    if _is_reviewed_mapping_check(check_name):
        return "normalize_with_verified_approved_mapping_review"
    if item_recommendation and item_recommendation != "accepted":
        return item_recommendation
    if check_name in {"data_kind_consistency", "data_adapter_consistency"}:
        return "rerun_vendor_market_data_pipeline_with_consistent_adapter_and_kind"
    if check_name == "explicit_fee_model":
        return "rerun_market_profile_with_explicit_fee_assumptions"
    if check_name.endswith("_provided"):
        return f"run_{component}"
    if check_name.endswith("_ready"):
        return f"fix_{component}"
    return f"fix_{component}_check"


def _is_reviewed_mapping_check(check_name: str) -> bool:
    return check_name.startswith("mapped_data_") and any(
        token in check_name
        for token in (
            "review_bound",
            "mapping_review",
            "operator_approved_mapping",
            "reviewed_normalization",
            "authorizes_",
            "source_file_sha256_present",
            "reviewed_mapping_sha256_present",
            "vendor_source_consistency",
        )
    )


def _is_target_application_mapping_check(check_name: str) -> bool:
    return check_name.startswith("mapped_data_target_application_")


def _runbook_markdown(
    summary_row: pd.Series,
    items: pd.DataFrame,
    checks: pd.DataFrame,
    action_queue: pd.DataFrame,
) -> str:
    ready_label = "yes" if _to_bool(summary_row.get("ready", False)) else "no"
    lines = [
        "# Data Readiness Runbook",
        "",
        f"- Ready: {ready_label}",
        "- Non-authorizing: yes",
        "- Authorizes routing: no",
        "- Authorizes submission: no",
        f"- Recommendation: {_value_text(summary_row.get('recommendation'))}",
        f"- Failed checks: {int(_value_number(summary_row.get('failed_checks')))}",
        f"- Ready components: {int(_value_number(summary_row.get('ready_components')))}",
        f"- Required components: {int(_value_number(summary_row.get('required_components')))}",
        f"- Market calendar: {_code(summary_row.get('market_calendar_id'))}",
        f"- Calendar SHA-256: {_code(summary_row.get('market_calendar_sha256'))}",
        f"- Calendar report verified: {_yes_no(_to_bool(summary_row.get('market_calendar_report_verified', False)))}",
        f"- Calendar report error: {_code(summary_row.get('market_calendar_report_verification_error'))}",
        f"- Calendar-bound components: {_value_text(summary_row.get('market_calendar_binding_components'))}",
        f"- Blocked actions: {int(_value_number(summary_row.get('blocked_action_count')))}",
        f"- Primary next gate: {_code(summary_row.get('next_gate'))}",
        f"- Primary next gate help: {_code(summary_row.get('next_gate_help_command'))}",
        "",
        "## Blocked Actions",
        "",
        _action_queue_table(action_queue),
        "",
        "## Components",
        "",
        _items_table(items),
        "",
        "## Failed Checks",
        "",
        _failed_checks_table(checks),
        "",
    ]
    return "\n".join(lines)


def _action_queue_table(action_queue: pd.DataFrame) -> str:
    if action_queue.empty:
        return "_None_"
    return _markdown_table(
        ["Priority", "Check", "Component", "Next gate", "Help", "Recommendation"],
        [
            [
                str(int(_value_number(row.get("priority")))),
                _value_text(row.get("check")),
                _value_text(row.get("component")),
                _code(row.get("next_gate")),
                _code(row.get("next_gate_help_command")),
                _value_text(row.get("recommendation")),
            ]
            for row in action_queue.to_dict(orient="records")
        ],
    )


def _items_table(items: pd.DataFrame) -> str:
    if items.empty:
        return "_None_"
    return _markdown_table(
        ["Component", "Required", "Provided", "Ready", "Rows", "Recommendation"],
        [
            [
                _value_text(row.get("component")),
                _yes_no(_to_bool(row.get("required"))),
                _yes_no(_to_bool(row.get("provided"))),
                _yes_no(_to_bool(row.get("ready"))),
                str(int(_value_number(row.get("rows")))),
                _value_text(row.get("recommendation")),
            ]
            for row in items.to_dict(orient="records")
        ],
    )


def _failed_checks_table(checks: pd.DataFrame) -> str:
    if checks.empty or "passed" not in checks.columns:
        return "_None_"
    failed = checks.loc[~checks["passed"].astype(bool)]
    if failed.empty:
        return "_None_"
    return _markdown_table(
        ["Check", "Actual", "Op", "Expected", "Reason"],
        [
            [
                _value_text(row.get("check")),
                _value_text(row.get("value")),
                _value_text(row.get("operator")),
                _value_text(row.get("threshold")),
                _value_text(row.get("reason")),
            ]
            for row in failed.to_dict(orient="records")
        ],
    )


def _markdown_table(headers: list[str], rows: list[list[str]]) -> str:
    if not rows:
        return "_None_"
    header = "| " + " | ".join(_escape_cell(value) for value in headers) + " |"
    separator = "| " + " | ".join("---" for _ in headers) + " |"
    body = ["| " + " | ".join(_escape_cell(value) for value in row) + " |" for row in rows]
    return "\n".join([header, separator, *body])


def _code(value: object) -> str:
    text = _value_text(value)
    return f"`{text}`" if text else ""


def _escape_cell(value: object) -> str:
    return _value_text(value).replace("|", "\\|").replace("\n", " ")


def _yes_no(value: bool) -> str:
    return "yes" if value else "no"


def _component_required(component: str, thresholds: DataReadinessThresholds) -> bool:
    return bool(
        {
            "market_calendar": (
                thresholds.require_market_calendar
                or thresholds.require_contract_expiry_validation
            ),
            "vendor_intake": thresholds.require_vendor_intake,
            "schema_audit": thresholds.require_schema_audit,
            "mapped_data": (
                thresholds.require_mapped_data
                or thresholds.require_reviewed_mapping_normalization
                or thresholds.require_target_application_normalization
            ),
            "tick_diagnostics": thresholds.require_tick_diagnostics,
            "chain_diagnostics": (
                thresholds.require_chain_diagnostics
                or thresholds.require_contract_expiry_validation
                or thresholds.require_contract_lot_validation
            ),
            "market_profile": thresholds.require_market_profile,
            "market_portability": thresholds.require_market_portability,
            "instrument_metadata": thresholds.require_instrument_metadata,
        }[component]
    )


def _component_ready(component: str, frame: pd.DataFrame) -> bool:
    row = _overall_row(frame)
    if component == "market_calendar":
        report_verified = (
            _to_bool(row.get("market_calendar_report_verified", False))
            if "market_calendar_report_verified" in row.index
            else True
        )
        return bool(
            _to_bool(row.get("ready", False))
            and report_verified
        )
    if component == "vendor_intake":
        return _to_bool(row.get("ready", False))
    if component == "schema_audit":
        return _to_bool(row.get("all_required_present", False))
    if component == "mapped_data":
        return _to_bool(row.get("ready", False))
    if component == "instrument_metadata":
        return _to_bool(row.get("passed", False))
    if component == "market_portability":
        return _to_bool(row.get("expected_pair_ready", row.get("ready", False)))
    if component == "market_profile":
        return int(_number(row, "markets", fallback=0.0)) > 0
    if component in {"tick_diagnostics", "chain_diagnostics"}:
        return int(_number(row, "rows", fallback=0.0)) > 0
    return False


def _component_failed_checks(component: str, row: pd.Series) -> float:
    failed = _number(
        row,
        "failed_checks",
        fallback=_number(
            row,
            "failed_mappings",
            fallback=_number(row, "unmapped_required_columns", fallback=0.0),
        ),
    )
    if component == "vendor_intake" and _to_bool(row.get("selected_kind_ambiguous", False)):
        return max(failed, 1.0)
    return failed


def _component_recommendation(
    component: str,
    provided: bool,
    ready: bool,
    required: bool,
    row: pd.Series,
) -> str:
    if not provided and required:
        return f"run_{component}"
    if not provided:
        return "optional_not_supplied"
    if component == "vendor_intake" and _to_bool(row.get("selected_kind_ambiguous", False)):
        return "set_vendor_kind_explicitly"
    if not ready:
        return f"fix_{component}"
    return "accepted"


def _component_text(items: pd.DataFrame, component: str, column: str) -> str:
    if items.empty or column not in items.columns:
        return ""
    row = items.loc[items["component"].astype(str) == component]
    if row.empty:
        return ""
    return _text(row.iloc[0], column)


def _component_bool(items: pd.DataFrame, component: str, column: str) -> bool:
    if items.empty or column not in items.columns:
        return False
    row = items.loc[items["component"].astype(str) == component]
    if row.empty:
        return False
    return _to_bool(row.iloc[0].get(column, False))


def _component_number(items: pd.DataFrame, component: str, column: str, fallback: float = np.nan) -> float:
    if items.empty or column not in items.columns:
        return fallback
    row = items.loc[items["component"].astype(str) == component]
    if row.empty:
        return fallback
    return _number(row.iloc[0], column, fallback=fallback)


def _joined_component_values(items: pd.DataFrame, column: str) -> str:
    if items.empty or column not in items.columns:
        return ""
    values = items[column].dropna().astype(str).str.strip()
    values = values.loc[values != ""]
    return ";".join(sorted(set(values)))


def _calendar_binding_components(items: pd.DataFrame) -> str:
    if items.empty or "market_calendar_provided" not in items.columns:
        return ""
    bound = items.loc[
        items["component"].isin(
            ["mapped_data", "tick_diagnostics", "chain_diagnostics"]
        )
        & items["market_calendar_provided"].map(_to_bool),
        "component",
    ]
    return ";".join(sorted(bound.astype(str).tolist()))


def _calendar_binding_count(items: pd.DataFrame) -> int:
    components = _calendar_binding_components(items)
    return len(components.split(";")) if components else 0


def _component_value_count(items: pd.DataFrame, column: str) -> int:
    values = _joined_component_values(items, column)
    if not values:
        return 0
    return len(values.split(";"))


def _component_kind(component: str, row: pd.Series) -> str:
    if component == "vendor_intake":
        return _vendor_data_kind(_text(row, "best_kind", fallback=_text(row, "kind")))
    return _vendor_data_kind(_text(row, "kind"))


def _joined_component_kinds(items: pd.DataFrame) -> str:
    if items.empty or "component" not in items.columns or "kind" not in items.columns:
        return ""
    kinds = [
        _vendor_data_kind(item.get("kind", ""))
        for item in items.to_dict(orient="records")
        if str(item.get("component", "")) in {"vendor_intake", "schema_audit", "mapped_data"}
    ]
    kinds = [kind for kind in kinds if kind]
    return ";".join(sorted(set(kinds)))


def _component_kind_count(items: pd.DataFrame) -> int:
    values = _joined_component_kinds(items)
    if not values:
        return 0
    return len(values.split(";"))


def _overall_row(frame: pd.DataFrame) -> pd.Series:
    if frame.empty:
        return pd.Series(dtype=object)
    if "scope" in frame.columns:
        overall = frame.loc[frame["scope"].astype(str) == "overall"]
        if not overall.empty:
            return overall.iloc[0]
    return frame.iloc[0]


def _read_optional_summary(path: str | Path | None, component: str) -> pd.DataFrame | None:
    if path is None:
        return None
    candidate = Path(path)
    if candidate.is_dir():
        candidate = candidate / SUMMARY_FILES[component]
    if not candidate.exists():
        raise FileNotFoundError(f"{component} summary not found: {candidate}")
    frame = pd.read_csv(candidate)
    if frame.empty:
        raise ValueError(f"{component} summary is empty: {candidate}")
    return frame


def _with_market_calendar_verification(
    summary: pd.DataFrame | None,
    verification: MarketCalendarReportVerification | None,
) -> pd.DataFrame | None:
    if summary is None or verification is None:
        return summary
    frame = summary.copy()
    frame["market_calendar_report_verified"] = verification.verified
    frame["market_calendar_report_manifest_current"] = (
        verification.manifest_current
    )
    frame["market_calendar_report_source_current"] = (
        verification.source_current
    )
    frame["market_calendar_report_artifacts_consistent"] = (
        verification.artifacts_consistent
    )
    frame["market_calendar_report_non_authorizing"] = (
        verification.non_authorizing
    )
    frame["market_calendar_report_verification_error"] = verification.error
    if not verification.verified:
        frame["ready"] = False
    return frame


def _read_optional_market_portability_config(path: str | Path | None) -> dict[str, Any] | None:
    if path is None:
        return None
    candidate = Path(path)
    if candidate.is_dir():
        candidate = candidate / SUMMARY_FILES["market_portability"]
    if not candidate.exists():
        raise FileNotFoundError(f"market portability config not found: {candidate}")
    return json.loads(candidate.read_text(encoding="utf-8"))


def _optional_frame(frame: pd.DataFrame | None) -> pd.DataFrame:
    return pd.DataFrame() if frame is None else frame.copy().reset_index(drop=True)


def _optional_config(config: dict[str, Any] | None) -> dict[str, Any]:
    return {} if config is None else dict(config)


def _market_portability_frame(
    config: dict[str, Any],
    thresholds: DataReadinessThresholds,
) -> pd.DataFrame:
    if not config:
        return pd.DataFrame()
    ready_pairs = config.get("ready_pairs") or []
    gap_pairs = config.get("gap_pairs") or []
    pair_ready = _portability_pair_ready(config, thresholds)
    return pd.DataFrame(
        [
            {
                "ready": _to_bool(config.get("ready", False)),
                "rows": int(len(ready_pairs) + len(gap_pairs)),
                "ready_pairs": int(len(ready_pairs)),
                "gap_pairs": int(len(gap_pairs)),
                "failed_checks": 0 if pair_ready else 1,
                "expected_strategy": _identity(thresholds.expected_strategy),
                "expected_market": _identity(thresholds.expected_market),
                "expected_pair_ready": pair_ready,
            }
        ]
    )


def _portability_pair_ready(config: dict[str, Any], thresholds: DataReadinessThresholds) -> bool:
    expected_strategy = _identity(thresholds.expected_strategy)
    expected_market = _identity(thresholds.expected_market)
    if not expected_strategy and not expected_market:
        return _to_bool(config.get("ready", False))
    if not expected_strategy or not expected_market:
        return False
    for pair in config.get("ready_pairs") or []:
        if _identity(pair.get("strategy")) != expected_strategy:
            continue
        if _identity(pair.get("market")) != expected_market:
            continue
        return str(pair.get("status", "")).strip().lower() in {"india_ready", "portable_research"}
    return False


def _identity(value: object) -> str:
    if value is None:
        return ""
    return str(value).strip().lower().replace("-", "_").replace(" ", "_").replace(".", "_")


def _vendor_data_kind(value: object) -> str:
    key = _identity(value)
    aliases = {
        "": "",
        "tick": "ticks",
        "ticks": "ticks",
        "top_of_book": "ticks",
        "chain": "chain",
        "option_chain": "chain",
        "options": "chain",
        "order": "orders",
        "orders": "orders",
        "simulated_orders": "orders",
        "fill": "fills",
        "fills": "fills",
        "live_fills": "fills",
    }
    return aliases.get(key, key)


def _threshold_check(name: str, value: float | int, operator: str, threshold: float | int) -> dict[str, Any]:
    value_float = float(value)
    threshold_float = float(threshold)
    missing = np.isnan(value_float) or np.isnan(threshold_float)
    if operator == ">=":
        passed = (not missing) and value_float + 1e-12 >= threshold_float
    elif operator == "<=":
        passed = (not missing) and value_float <= threshold_float + 1e-12
    else:
        raise ValueError(f"unsupported operator {operator!r}")
    reason = ""
    if missing:
        reason = f"{name} or threshold is unavailable"
    elif not passed:
        reason = f"{name} {value_float:.6g} failed {operator} {threshold_float:.6g}"
    return _check(name, value_float, operator, threshold_float, passed, reason)


def _check(
    name: str,
    value: object,
    operator: str,
    threshold: object,
    passed: bool,
    reason: str,
) -> dict[str, Any]:
    return {
        "check": name,
        "value": value,
        "operator": operator,
        "threshold": threshold,
        "passed": bool(passed),
        "reason": "" if passed else reason,
    }


def _max_number(frame: pd.DataFrame, column: str) -> float:
    if frame.empty or column not in frame.columns:
        return np.nan
    values = pd.to_numeric(frame[column], errors="coerce")
    return float(values.max(skipna=True)) if values.notna().any() else np.nan


def _number(row: pd.Series, column: str, fallback: float = np.nan) -> float:
    value = row.get(column, fallback)
    if pd.isna(value):
        return float(fallback)
    return float(value)


def _text(row: pd.Series, column: str, fallback: str = "") -> str:
    value = row.get(column, fallback)
    if pd.isna(value):
        return fallback
    return str(value).strip()


def _value_text(value: object) -> str:
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except (TypeError, ValueError):
        pass
    return str(value).strip()


def _value_number(value: object) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.0
    try:
        if pd.isna(number):
            return 0.0
    except (TypeError, ValueError):
        pass
    return number


def _to_bool(value: object) -> bool:
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "ready", "passed"}
    if value is None:
        return False
    try:
        if bool(pd.isna(value)):
            return False
    except (TypeError, ValueError):
        pass
    return bool(value)


def _validate_thresholds(thresholds: DataReadinessThresholds) -> None:
    if (
        thresholds.require_reviewed_mapping_normalization
        and thresholds.require_target_application_normalization
    ):
        raise ValueError(
            "reviewed and target-application normalization requirements are mutually exclusive"
        )
    expected_kind = _vendor_data_kind(thresholds.expected_vendor_data_kind)
    if expected_kind and expected_kind not in {"ticks", "chain", "orders", "fills"}:
        raise ValueError("expected_vendor_data_kind must be one of ticks, chain, orders, or fills")
    for name in (
        "min_tick_rows",
        "min_chain_rows",
        "min_chain_expiries",
        "min_chain_strikes",
        "min_chain_expiry_snapshots",
        "min_chain_snapshots_per_expiry",
        "min_chain_snapshot_strikes",
        "max_null_rows",
        "max_nonfinite_rows",
        "max_nonintegral_rows",
        "max_duplicate_tick_rows",
        "max_integer_overflow_rows",
        "max_nonmonotonic_rows",
        "max_crossed_quote_rows",
        "max_nonpositive_quote_rows",
        "max_nonpositive_depth_rows",
        "max_invalid_trade_rows",
        "max_non_trading_day_rows",
        "max_out_of_session_rows",
        "max_unparseable_contract_expiry_rows",
        "max_expired_contract_rows",
        "max_duplicate_contract_key_rows",
        "max_conflicting_contract_key_rows",
        "max_invalid_contract_expiry_rows",
        "max_uncovered_contract_expiry_rows",
        "max_invalid_contract_lot_rows",
        "max_uncovered_contract_lot_rows",
    ):
        if getattr(thresholds, name) < 0:
            raise ValueError(f"{name} must be non-negative")
    for name in (
        "max_off_tick_price_rows",
        "max_tick_p99_gap_ns",
        "max_tick_median_spread_ticks",
        "max_chain_median_spread_ticks",
        "max_chain_snapshot_p99_gap_ns",
    ):
        value = getattr(thresholds, name)
        if value is not None and value < 0:
            raise ValueError(f"{name} must be non-negative")
