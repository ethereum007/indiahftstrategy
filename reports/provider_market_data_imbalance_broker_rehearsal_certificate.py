from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping

import pandas as pd

from reports.manifest import file_sha256, write_experiment_manifest


RUN_TYPE = "provider_market_data_imbalance_broker_rehearsal_certificate"
SOURCE_RUN_TYPE = "provider_market_data_imbalance_broker_dispatch_roundtrip"
NESTED_ROUNDTRIP_RUN_TYPE = "broker_dispatch_roundtrip"
READY_NEXT_GATE = "review-provider-market-data-imbalance-broker-readiness"
REPAIR_ROUNDTRIP_GATE = "review-provider-market-data-imbalance-broker-dispatch-roundtrip"

SAFE_TARGET_MODES = ("paper", "shadow", "live_dryrun")

ACTION_QUEUE_COLUMNS = [
    "priority",
    "queue_status",
    "source",
    "component",
    "check",
    "actual",
    "operator",
    "expected",
    "action",
    "reason",
    "recommendation",
    "next_gate",
    "next_gate_help_command",
]

FINGERPRINT_COLUMNS = [
    "manifest_path",
    "manifest_run_type",
    "scope",
    "name",
    "path",
    "kind",
    "expected_size_bytes",
    "current_size_bytes",
    "expected_sha256",
    "current_sha256",
    "expected_file_count",
    "current_file_count",
    "expected_tree_sha256",
    "current_tree_sha256",
    "exists",
    "matches",
    "reason",
]

MANIFEST_GRAPH_COLUMNS = [
    "depth",
    "manifest_path",
    "manifest_sha256",
    "run_type",
    "schema_version",
    "readable",
    "git_commit",
    "git_dirty",
    "artifact_fingerprint_count",
    "input_fingerprint_count",
    "failed_fingerprint_count",
    "passed",
    "reason",
]


@dataclass(frozen=True)
class ProviderMarketDataImbalanceBrokerRehearsalCertificateConfig:
    allowed_target_modes: tuple[str, ...] = SAFE_TARGET_MODES
    require_clean_recorded_git: bool = True
    require_sealed_provider_receipts: bool = False
    max_manifest_count: int = 64


@dataclass(frozen=True)
class ProviderMarketDataImbalanceBrokerRehearsalCertificateReport:
    checks: pd.DataFrame
    summary: pd.DataFrame
    fingerprint_inventory: pd.DataFrame
    manifest_graph: pd.DataFrame
    action_queue: pd.DataFrame
    certificate: dict[str, Any]
    output_dir: Path | None = None

    @property
    def ready(self) -> bool:
        if self.summary.empty:
            return False
        return bool(self.summary.iloc[0]["ready"])

    @property
    def valid(self) -> bool:
        return self.ready


def write_provider_market_data_imbalance_broker_rehearsal_certificate(
    provider_broker_dispatch_roundtrip_dir: str | Path,
    output_dir: str | Path,
    *,
    config: ProviderMarketDataImbalanceBrokerRehearsalCertificateConfig | None = None,
) -> ProviderMarketDataImbalanceBrokerRehearsalCertificateReport:
    config = config or ProviderMarketDataImbalanceBrokerRehearsalCertificateConfig()
    _validate_config(config)

    source_root = Path(provider_broker_dispatch_roundtrip_dir).resolve()
    out = Path(output_dir).resolve()
    _validate_output_location(source_root, out)
    out.mkdir(parents=True, exist_ok=True)

    source_summary, source_summary_error = _read_csv(
        source_root / "provider_market_data_imbalance_broker_dispatch_roundtrip_summary.csv"
    )
    source_checks, source_checks_error = _read_csv(
        source_root / "provider_market_data_imbalance_broker_dispatch_roundtrip_checks.csv"
    )
    source_config, source_config_error = _read_json(
        source_root / "provider_market_data_imbalance_broker_dispatch_roundtrip_config.json"
    )
    source_manifest, source_manifest_error = _read_json(source_root / "manifest.json")

    source_row = source_summary.iloc[0] if not source_summary.empty else pd.Series(dtype=object)
    nested_root = _nested_roundtrip_root(source_root, source_row, source_config)
    nested_summary, nested_summary_error = _read_csv(
        nested_root / "broker_dispatch_roundtrip_summary.csv"
    )
    nested_checks, nested_checks_error = _read_csv(
        nested_root / "broker_dispatch_roundtrip_checks.csv"
    )
    nested_manifest, nested_manifest_error = _read_json(nested_root / "manifest.json")
    nested_row = nested_summary.iloc[0] if not nested_summary.empty else pd.Series(dtype=object)

    manifest_graph, fingerprint_inventory, graph_truncated = _build_manifest_graph(
        source_root / "manifest.json",
        max_manifest_count=config.max_manifest_count,
    )

    checks = _certificate_checks(
        source_summary=source_summary,
        source_summary_error=source_summary_error,
        source_checks=source_checks,
        source_checks_error=source_checks_error,
        source_config=source_config,
        source_config_error=source_config_error,
        source_manifest=source_manifest,
        source_manifest_error=source_manifest_error,
        nested_summary=nested_summary,
        nested_summary_error=nested_summary_error,
        nested_checks=nested_checks,
        nested_checks_error=nested_checks_error,
        nested_manifest=nested_manifest,
        nested_manifest_error=nested_manifest_error,
        manifest_graph=manifest_graph,
        fingerprint_inventory=fingerprint_inventory,
        graph_truncated=graph_truncated,
        config=config,
    )
    valid = bool(not checks.empty and checks["passed"].astype(bool).all())

    certificate = _certificate_payload(
        valid=valid,
        source_root=source_root,
        source_row=source_row,
        source_config=source_config,
        source_manifest=source_manifest,
        nested_root=nested_root,
        nested_row=nested_row,
        nested_checks=nested_checks,
        manifest_graph=manifest_graph,
        fingerprint_inventory=fingerprint_inventory,
        config=config,
    )
    summary = _summary(
        valid=valid,
        source_root=source_root,
        source_row=source_row,
        nested_root=nested_root,
        nested_row=nested_row,
        checks=checks,
        manifest_graph=manifest_graph,
        fingerprint_inventory=fingerprint_inventory,
        certificate=certificate,
    )
    action_queue = _action_queue(checks)
    summary = _summary_with_actions(summary, action_queue)

    checks.to_csv(
        out / "provider_market_data_imbalance_broker_rehearsal_certificate_checks.csv",
        index=False,
    )
    summary.to_csv(
        out / "provider_market_data_imbalance_broker_rehearsal_certificate_summary.csv",
        index=False,
    )
    fingerprint_inventory.to_csv(
        out / "provider_market_data_imbalance_broker_rehearsal_certificate_fingerprints.csv",
        index=False,
    )
    manifest_graph.to_csv(
        out / "provider_market_data_imbalance_broker_rehearsal_certificate_manifest_graph.csv",
        index=False,
    )
    action_queue.to_csv(
        out / "provider_market_data_imbalance_broker_rehearsal_certificate_action_queue.csv",
        index=False,
    )
    (out / "provider_market_data_imbalance_broker_rehearsal_certificate.json").write_text(
        json.dumps(_jsonable(certificate), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (out / "provider_market_data_imbalance_broker_rehearsal_certificate_runbook.md").write_text(
        _runbook_markdown(summary.iloc[0], checks, action_queue),
        encoding="utf-8",
    )

    chain_manifest_paths = [
        Path(path)
        for path in manifest_graph.get("manifest_path", pd.Series(dtype=str)).astype(str).tolist()
        if path
    ]
    write_experiment_manifest(
        out,
        run_type=RUN_TYPE,
        parameters={"config": asdict(config)},
        inputs={
            "provider_broker_dispatch_roundtrip": source_root,
            "provider_broker_dispatch_roundtrip_manifest": source_root / "manifest.json",
            "manifest_chain": chain_manifest_paths,
        },
        extra={
            "ready": valid,
            "valid": valid,
            "authorizes_submission": False,
            "digitally_signed": False,
            "cycle_id": certificate["cycle_id"],
            "certificate_sha256": certificate["certificate_sha256"],
            "assurance_level": certificate["payload"]["assurance_level"],
            "strategy": _text(source_row, "strategy"),
            "market": _text(source_row, "market"),
            "exchange": _text(source_row, "exchange"),
            "target_mode": _text(source_row, "target_mode"),
            "source_manifest_sha256": certificate["payload"]["source"]["manifest_sha256"],
            "manifest_chain_sha256": certificate["payload"]["integrity"]["manifest_chain_sha256"],
        },
    )

    return ProviderMarketDataImbalanceBrokerRehearsalCertificateReport(
        checks=checks,
        summary=summary,
        fingerprint_inventory=fingerprint_inventory,
        manifest_graph=manifest_graph,
        action_queue=action_queue,
        certificate=certificate,
        output_dir=out,
    )


def _certificate_checks(
    *,
    source_summary: pd.DataFrame,
    source_summary_error: str,
    source_checks: pd.DataFrame,
    source_checks_error: str,
    source_config: dict[str, Any],
    source_config_error: str,
    source_manifest: dict[str, Any],
    source_manifest_error: str,
    nested_summary: pd.DataFrame,
    nested_summary_error: str,
    nested_checks: pd.DataFrame,
    nested_checks_error: str,
    nested_manifest: dict[str, Any],
    nested_manifest_error: str,
    manifest_graph: pd.DataFrame,
    fingerprint_inventory: pd.DataFrame,
    graph_truncated: bool,
    config: ProviderMarketDataImbalanceBrokerRehearsalCertificateConfig,
) -> pd.DataFrame:
    source_row = source_summary.iloc[0] if not source_summary.empty else pd.Series(dtype=object)
    nested_row = nested_summary.iloc[0] if not nested_summary.empty else pd.Series(dtype=object)
    rows: list[dict[str, Any]] = []

    rows.extend(
        [
            _check("source_summary_readable", not source_summary_error, "is", True, "source", source_summary_error),
            _check("source_checks_readable", not source_checks_error, "is", True, "source", source_checks_error),
            _check("source_config_readable", not source_config_error, "is", True, "source", source_config_error),
            _check("source_manifest_readable", not source_manifest_error, "is", True, "source", source_manifest_error),
            _check("nested_roundtrip_summary_readable", not nested_summary_error, "is", True, "roundtrip", nested_summary_error),
            _check("nested_roundtrip_checks_readable", not nested_checks_error, "is", True, "roundtrip", nested_checks_error),
            _check("nested_roundtrip_manifest_readable", not nested_manifest_error, "is", True, "roundtrip", nested_manifest_error),
        ]
    )

    rows.extend(
        [
            _check(
                "source_manifest_run_type",
                _text_value(source_manifest.get("run_type")),
                "==",
                SOURCE_RUN_TYPE,
                "source",
                "final provider roundtrip manifest has the wrong run type",
            ),
            _check(
                "nested_roundtrip_manifest_run_type",
                _text_value(nested_manifest.get("run_type")),
                "==",
                NESTED_ROUNDTRIP_RUN_TYPE,
                "roundtrip",
                "nested broker roundtrip manifest has the wrong run type",
            ),
            _check(
                "source_roundtrip_passed",
                _bool(source_row.get("passed", False)),
                "is",
                True,
                "source",
                "final provider roundtrip did not pass",
            ),
            _check(
                "source_roundtrip_ready",
                _bool(source_row.get("ready", False)),
                "is",
                True,
                "source",
                "final provider roundtrip is not ready",
            ),
            _check(
                "source_failed_checks",
                _integer(source_row.get("failed_checks", -1)),
                "==",
                0,
                "source",
                "final provider roundtrip reports failed checks",
            ),
            _check(
                "source_checks_all_passed",
                _all_checks_passed(source_checks),
                "is",
                True,
                "source",
                "final provider roundtrip check file contains a failed check",
            ),
            _check(
                "nested_roundtrip_passed",
                _bool(nested_row.get("passed", False)),
                "is",
                True,
                "roundtrip",
                "nested broker dispatch roundtrip did not pass",
            ),
            _check(
                "target_mode_safe",
                _identity(source_row.get("target_mode", "")),
                "in",
                list(config.allowed_target_modes),
                "safety",
                "certificate target mode must remain paper, shadow, or live_dryrun",
            ),
            _check(
                "target_mode_matches_nested_roundtrip",
                _identity(nested_row.get("target_mode", "")),
                "==",
                _identity(source_row.get("target_mode", "")),
                "identity",
                "provider and nested roundtrip target modes differ",
            ),
        ]
    )

    rows.extend(_identity_checks(source_row, nested_row, source_config, source_manifest))
    rows.extend(_strict_roundtrip_checks(nested_checks, nested_row))
    rows.extend(_acknowledgement_checks(source_row, nested_row))
    rows.extend(_receipt_checks(source_row, config))

    graph_passed = bool(
        not manifest_graph.empty and manifest_graph["passed"].astype(bool).all()
    )
    fingerprints_passed = bool(
        not fingerprint_inventory.empty
        and fingerprint_inventory["matches"].astype(bool).all()
    )
    graph_clean = bool(
        not manifest_graph.empty
        and (~manifest_graph["git_dirty"].map(_bool)).all()
        and manifest_graph["git_commit"].astype(str).str.strip().ne("").all()
    )
    rows.extend(
        [
            _check(
                "manifest_graph_not_truncated",
                graph_truncated,
                "is",
                False,
                "integrity",
                "manifest graph exceeded the configured traversal limit",
            ),
            _check(
                "manifest_graph_valid",
                graph_passed,
                "is",
                True,
                "integrity",
                "one or more reachable manifests are unreadable or internally inconsistent",
            ),
            _check(
                "recorded_fingerprints_current",
                fingerprints_passed,
                "is",
                True,
                "integrity",
                "one or more recorded input or artifact fingerprints have drifted",
            ),
            _check(
                "recorded_git_state_clean",
                graph_clean,
                "is",
                True,
                "integrity",
                "one or more manifests were recorded from dirty or unidentified git state",
                required=config.require_clean_recorded_git,
            ),
            _check(
                "authorizes_submission",
                False,
                "is",
                False,
                "safety",
                "a rehearsal certificate must never authorize broker submission",
            ),
        ]
    )

    return pd.DataFrame(rows)


def _identity_checks(
    source_row: pd.Series,
    nested_row: pd.Series,
    source_config: dict[str, Any],
    source_manifest: dict[str, Any],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    config_summary = _mapping(source_config.get("summary"))
    manifest_extra = _mapping(source_manifest.get("extra"))
    for field in ("strategy", "market", "target_mode", "adapter", "scenario_key"):
        source_value = _identity(source_row.get(field, "")) if field != "scenario_key" else _text(source_row, field)
        nested_value = _identity(nested_row.get(field, "")) if field != "scenario_key" else _text(nested_row, field)
        rows.append(
            _check(
                f"{field}_matches_nested_roundtrip",
                nested_value,
                "==",
                source_value,
                "identity",
                f"provider and nested roundtrip {field} differ",
            )
        )
        config_value = _identity(config_summary.get(field, "")) if field != "scenario_key" else _text_value(config_summary.get(field))
        rows.append(
            _check(
                f"{field}_matches_source_config",
                config_value,
                "==",
                source_value,
                "identity",
                f"provider summary and config {field} differ",
            )
        )
    for field in ("strategy", "market", "exchange"):
        source_value = _identity(source_row.get(field, ""))
        manifest_value = _identity(manifest_extra.get(field, ""))
        rows.append(
            _check(
                f"{field}_matches_source_manifest",
                manifest_value,
                "==",
                source_value,
                "identity",
                f"provider summary and manifest {field} differ",
            )
        )
    return rows


def _strict_roundtrip_checks(
    nested_checks: pd.DataFrame,
    nested_summary: pd.Series,
) -> list[dict[str, Any]]:
    dispatch_orders = _integer(nested_summary.get("dispatch_orders", 0))
    send_requests = _integer(nested_summary.get("send_requests", 0))
    required = {
        "dispatch_ready": ("is", True),
        "send_ready": ("is", True),
        "ack_passed": ("is", True),
        "identity_match": ("==", 0),
        "request_count_matches_dispatch": ("exact_count", dispatch_orders),
        "unique_request_per_dispatch_order": ("exact_count", dispatch_orders),
        "submission_disabled": ("is", False),
        "dry_run_only": ("is", True),
        "all_requests_acked": ("exact_count", send_requests),
        "missing_request_acks": ("==", 0),
        "rejected_orders": ("==", 0),
        "duplicate_ack_orders": ("==", 0),
        "unmatched_acks": ("==", 0),
        "component_failed_checks": ("==", 0),
        "route_enable_dispatch_roundtrip_failed_checks": ("==", 0),
    }
    rows: list[dict[str, Any]] = []
    for name, (operator, expected) in required.items():
        match = (
            nested_checks.loc[nested_checks["check"].astype(str) == name]
            if not nested_checks.empty and "check" in nested_checks.columns
            else pd.DataFrame()
        )
        if match.empty:
            rows.append(
                _check(
                    f"strict_{name}",
                    "missing",
                    "exists",
                    True,
                    "safety",
                    f"nested roundtrip is missing required safety check {name}",
                )
            )
            continue
        row = match.iloc[0]
        actual = row.get("value")
        threshold = row.get("threshold")
        if operator == "exact_count":
            passed = (
                _integer(expected) > 0
                and _scalar_equal(actual, expected)
                and _scalar_equal(threshold, expected)
                and _bool(row.get("passed", False))
            )
            rows.append(
                _check_result(
                    f"strict_{name}",
                    actual,
                    "==",
                    expected,
                    passed,
                    "safety",
                    f"nested roundtrip safety check {name} is not exact",
                )
            )
            continue
        passed = _scalar_equal(actual, expected)
        rows.append(
            _check_result(
                f"strict_{name}",
                actual,
                operator,
                expected,
                passed,
                "safety",
                f"nested roundtrip safety check {name} is not strict",
            )
        )
    return rows


def _acknowledgement_checks(source_row: pd.Series, nested_row: pd.Series) -> list[dict[str, Any]]:
    dispatch_orders = _integer(source_row.get("dispatch_orders", nested_row.get("dispatch_orders", 0)))
    send_requests = _integer(source_row.get("send_requests", nested_row.get("send_requests", 0)))
    acked_orders = _integer(source_row.get("acked_orders", nested_row.get("acked_orders", 0)))
    return [
        _check_result(
            "dispatch_orders_match_send_requests",
            send_requests,
            "==",
            dispatch_orders,
            send_requests == dispatch_orders and dispatch_orders > 0,
            "acknowledgement",
            "dispatch and send counts differ or are empty",
        ),
        _check_result(
            "send_requests_match_acked_orders",
            acked_orders,
            "==",
            send_requests,
            acked_orders == send_requests and send_requests > 0,
            "acknowledgement",
            "send and acknowledgement counts differ or are empty",
        ),
        *[
            _check(
                f"zero_{field}",
                _integer(source_row.get(field, nested_row.get(field, -1))),
                "==",
                0,
                "acknowledgement",
                f"rehearsal contains {field.replace('_', ' ')}",
            )
            for field in (
                "missing_request_acks",
                "rejected_orders",
                "duplicate_ack_orders",
                "unmatched_acks",
            )
        ],
    ]


def _receipt_checks(
    source_row: pd.Series,
    config: ProviderMarketDataImbalanceBrokerRehearsalCertificateConfig,
) -> list[dict[str, Any]]:
    required_count = _integer(
        source_row.get("dispatch_roundtrip_adapter_receipt_required_count", 0)
    )
    receipts_required = _bool(
        source_row.get("dispatch_roundtrip_adapter_receipts_required", False)
    ) or required_count > 0
    proof_expected = receipts_required or config.require_sealed_provider_receipts
    valid_count = _integer(
        source_row.get("dispatch_roundtrip_adapter_receipt_valid_count", 0)
    )
    receipt_matches = _integer(
        source_row.get("dispatch_roundtrip_adapter_receipt_fingerprint_match_count", 0)
    )
    capture_matches = _integer(
        source_row.get("dispatch_roundtrip_capture_fingerprint_match_count", 0)
    )
    rows = [
        _check_result(
            "sealed_provider_receipts_present",
            required_count,
            ">",
            0,
            required_count > 0,
            "receipt",
            "sealed provider receipts are required for this certificate",
            required=config.require_sealed_provider_receipts,
        ),
        _check_result(
            "provider_receipt_proof_ready",
            _bool(source_row.get("dispatch_roundtrip_adapter_receipt_proof_ready", False)),
            "is",
            True,
            _bool(source_row.get("dispatch_roundtrip_adapter_receipt_proof_ready", False)),
            "receipt",
            "final provider receipt proof is not ready",
            required=proof_expected,
        ),
        _check_result(
            "provider_receipt_proof_matches_manifest",
            _bool(source_row.get("dispatch_roundtrip_adapter_receipt_proof_matches_manifest", False)),
            "is",
            True,
            _bool(source_row.get("dispatch_roundtrip_adapter_receipt_proof_matches_manifest", False)),
            "receipt",
            "final provider receipt proof does not match the acknowledgement manifest",
            required=proof_expected,
        ),
        _check_result(
            "provider_receipt_proof_matches_runtime_session",
            _bool(
                source_row.get(
                    "dispatch_roundtrip_adapter_receipt_proof_matches_runtime_session",
                    False,
                )
            ),
            "is",
            True,
            _bool(
                source_row.get(
                    "dispatch_roundtrip_adapter_receipt_proof_matches_runtime_session",
                    False,
                )
            ),
            "receipt",
            "final provider receipt proof does not match runtime-session proof",
            required=proof_expected,
        ),
    ]
    for name, value in (
        ("provider_receipt_valid_count", valid_count),
        ("provider_receipt_fingerprint_match_count", receipt_matches),
        ("provider_capture_fingerprint_match_count", capture_matches),
    ):
        rows.append(
            _check_result(
                name,
                value,
                "==",
                required_count,
                value == required_count,
                "receipt",
                "sealed provider receipt counts are incomplete",
                required=proof_expected,
            )
        )
    return rows


def _build_manifest_graph(
    root_manifest_path: Path,
    *,
    max_manifest_count: int,
) -> tuple[pd.DataFrame, pd.DataFrame, bool]:
    graph_rows: list[dict[str, Any]] = []
    fingerprint_rows: list[dict[str, Any]] = []
    queue: list[tuple[Path, int]] = [(root_manifest_path.resolve(), 0)]
    visited: set[Path] = set()
    truncated = False

    while queue:
        manifest_path, depth = queue.pop(0)
        if manifest_path in visited:
            continue
        if len(visited) >= max_manifest_count:
            truncated = True
            break
        visited.add(manifest_path)

        manifest, error = _read_json(manifest_path)
        readable = not error
        run_type = _text_value(manifest.get("run_type"))
        current_rows: list[dict[str, Any]] = []
        child_manifests: list[Path] = []
        if readable:
            current_rows.extend(_artifact_fingerprint_rows(manifest_path, manifest))
            input_rows, child_manifests = _input_fingerprint_rows(manifest_path, manifest)
            current_rows.extend(input_rows)
        fingerprint_rows.extend(current_rows)
        failed = sum(not bool(row["matches"]) for row in current_rows)
        git = _mapping(manifest.get("git"))
        graph_rows.append(
            {
                "depth": depth,
                "manifest_path": str(manifest_path),
                "manifest_sha256": file_sha256(manifest_path) if manifest_path.is_file() else "",
                "run_type": run_type,
                "schema_version": manifest.get("schema_version", ""),
                "readable": readable,
                "git_commit": _text_value(git.get("commit")),
                "git_dirty": _bool(git.get("dirty", False)),
                "artifact_fingerprint_count": sum(row["scope"] == "artifact" for row in current_rows),
                "input_fingerprint_count": sum(row["scope"] == "input" for row in current_rows),
                "failed_fingerprint_count": failed,
                "passed": readable and failed == 0,
                "reason": error if error else ("recorded fingerprints drifted" if failed else ""),
            }
        )
        for child in child_manifests:
            if child not in visited:
                queue.append((child, depth + 1))

    graph = pd.DataFrame(graph_rows, columns=MANIFEST_GRAPH_COLUMNS)
    fingerprints = pd.DataFrame(fingerprint_rows, columns=FINGERPRINT_COLUMNS)
    return graph, fingerprints, truncated


def _artifact_fingerprint_rows(manifest_path: Path, manifest: dict[str, Any]) -> list[dict[str, Any]]:
    root = manifest_path.parent
    run_type = _text_value(manifest.get("run_type"))
    rows: list[dict[str, Any]] = []
    artifacts = manifest.get("artifacts", [])
    if not isinstance(artifacts, list):
        return rows
    for index, item in enumerate(artifacts):
        fingerprint = _mapping(item)
        path = root / _text_value(fingerprint.get("path"))
        rows.append(
            _evaluate_fingerprint(
                manifest_path=manifest_path,
                manifest_run_type=run_type,
                scope="artifact",
                name=f"artifacts[{index}]",
                path=path,
                fingerprint={**fingerprint, "kind": "file"},
            )
        )
    return rows


def _input_fingerprint_rows(
    manifest_path: Path,
    manifest: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[Path]]:
    run_type = _text_value(manifest.get("run_type"))
    rows: list[dict[str, Any]] = []
    child_manifests: list[Path] = []
    for name, fingerprint in _iter_fingerprints(manifest.get("inputs", {})):
        path = Path(_text_value(fingerprint.get("path")))
        row = _evaluate_fingerprint(
            manifest_path=manifest_path,
            manifest_run_type=run_type,
            scope="input",
            name=name,
            path=path,
            fingerprint=fingerprint,
        )
        rows.append(row)
        if _text_value(fingerprint.get("kind")) == "directory":
            child = path / "manifest.json"
            if child.is_file():
                child_manifests.append(child.resolve())
    return rows, child_manifests


def _iter_fingerprints(value: Any, prefix: str = "inputs") -> Iterable[tuple[str, dict[str, Any]]]:
    if isinstance(value, Mapping):
        mapping = dict(value)
        if _text_value(mapping.get("kind")) in {"file", "directory"} and mapping.get("path"):
            yield prefix, mapping
            return
        for key, item in mapping.items():
            yield from _iter_fingerprints(item, f"{prefix}.{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            yield from _iter_fingerprints(item, f"{prefix}[{index}]")


def _evaluate_fingerprint(
    *,
    manifest_path: Path,
    manifest_run_type: str,
    scope: str,
    name: str,
    path: Path,
    fingerprint: dict[str, Any],
) -> dict[str, Any]:
    kind = _text_value(fingerprint.get("kind"))
    exists = path.exists()
    current_size = int(path.stat().st_size) if exists and path.is_file() else 0
    current_sha = file_sha256(path) if exists and path.is_file() else ""
    current_count = 0
    current_tree = ""
    if exists and path.is_dir():
        current_count, current_tree = _directory_tree_fingerprint(path)

    expected_size = _integer(fingerprint.get("size_bytes", 0))
    expected_sha = _text_value(fingerprint.get("sha256"))
    expected_count = _integer(fingerprint.get("file_count", 0))
    expected_tree = _text_value(fingerprint.get("tree_sha256"))
    if kind == "file":
        matches = exists and path.is_file() and current_size == expected_size and current_sha == expected_sha
    elif kind == "directory":
        matches = exists and path.is_dir() and current_count == expected_count and current_tree == expected_tree
    else:
        matches = False
    reason = ""
    if not exists:
        reason = "path does not exist"
    elif kind == "file" and not path.is_file():
        reason = "recorded file is not a file"
    elif kind == "directory" and not path.is_dir():
        reason = "recorded directory is not a directory"
    elif not matches:
        reason = "fingerprint drift"
    return {
        "manifest_path": str(manifest_path),
        "manifest_run_type": manifest_run_type,
        "scope": scope,
        "name": name,
        "path": str(path),
        "kind": kind,
        "expected_size_bytes": expected_size,
        "current_size_bytes": current_size,
        "expected_sha256": expected_sha,
        "current_sha256": current_sha,
        "expected_file_count": expected_count,
        "current_file_count": current_count,
        "expected_tree_sha256": expected_tree,
        "current_tree_sha256": current_tree,
        "exists": exists,
        "matches": matches,
        "reason": reason,
    }


def _directory_tree_fingerprint(path: Path) -> tuple[int, str]:
    files = [
        item
        for item in sorted(path.rglob("*"))
        if item.is_file() and item.name != "manifest.json"
    ]
    hasher = hashlib.sha256()
    for item in files:
        hasher.update(item.relative_to(path).as_posix().encode("utf-8"))
        hasher.update(file_sha256(item).encode("ascii"))
    return len(files), hasher.hexdigest()


def _certificate_payload(
    *,
    valid: bool,
    source_root: Path,
    source_row: pd.Series,
    source_config: dict[str, Any],
    source_manifest: dict[str, Any],
    nested_root: Path,
    nested_row: pd.Series,
    nested_checks: pd.DataFrame,
    manifest_graph: pd.DataFrame,
    fingerprint_inventory: pd.DataFrame,
    config: ProviderMarketDataImbalanceBrokerRehearsalCertificateConfig,
) -> dict[str, Any]:
    manifest_chain = [
        {
            "run_type": str(row["run_type"]),
            "manifest_sha256": str(row["manifest_sha256"]),
        }
        for _, row in manifest_graph.sort_values(
            ["depth", "run_type", "manifest_sha256"], kind="stable"
        ).iterrows()
    ]
    manifest_chain_sha = _canonical_sha256(manifest_chain)
    required_receipts = _integer(
        source_row.get("dispatch_roundtrip_adapter_receipt_required_count", 0)
    )
    receipt_ready = _bool(
        source_row.get("dispatch_roundtrip_adapter_receipt_proof_ready", False)
    )
    assurance_level = (
        "sealed_provider_receipts"
        if required_receipts > 0 and receipt_ready
        else "broker_dry_run_roundtrip"
    )
    strict = _strict_check_values(nested_checks)
    core = {
        "schema_version": 1,
        "certificate_type": "provider_market_data_imbalance_broker_rehearsal",
        "valid": valid,
        "authorizes_submission": False,
        "digitally_signed": False,
        "integrity_scheme": "sha256_manifest_chain_v1",
        "assurance_level": assurance_level,
        "source": {
            "run_type": SOURCE_RUN_TYPE,
            "path": str(source_root),
            "manifest_sha256": file_sha256(source_root / "manifest.json")
            if (source_root / "manifest.json").is_file()
            else "",
            "recorded_git_commit": _text_value(_mapping(source_manifest.get("git")).get("commit")),
        },
        "identity": {
            "profile": _text(source_row, "profile"),
            "provider": _text(source_row, "provider"),
            "transport": _text(source_row, "transport"),
            "strategy": _text(source_row, "strategy"),
            "market": _text(source_row, "market"),
            "exchange": _text(source_row, "exchange"),
            "target_mode": _text(source_row, "target_mode"),
            "adapter": _text(source_row, "adapter"),
            "scenario_key": _text(source_row, "scenario_key"),
        },
        "safety": {
            "allowed_target_modes": list(config.allowed_target_modes),
            "submission_enabled": _bool(strict.get("submission_disabled", True)),
            "dry_run_only": _bool(strict.get("dry_run_only", False)),
            "identity_mismatches": _integer(strict.get("identity_match", -1)),
            "authorizes_submission": False,
        },
        "acknowledgements": {
            "dispatch_orders": _integer(source_row.get("dispatch_orders", 0)),
            "send_requests": _integer(source_row.get("send_requests", 0)),
            "acked_orders": _integer(source_row.get("acked_orders", 0)),
            "missing_request_acks": _integer(source_row.get("missing_request_acks", 0)),
            "rejected_orders": _integer(source_row.get("rejected_orders", 0)),
            "duplicate_ack_orders": _integer(source_row.get("duplicate_ack_orders", 0)),
            "unmatched_acks": _integer(source_row.get("unmatched_acks", 0)),
        },
        "provider_receipts": {
            "required": _bool(
                source_row.get("dispatch_roundtrip_adapter_receipts_required", False)
            ),
            "required_count": required_receipts,
            "valid_count": _integer(
                source_row.get("dispatch_roundtrip_adapter_receipt_valid_count", 0)
            ),
            "receipt_fingerprint_match_count": _integer(
                source_row.get(
                    "dispatch_roundtrip_adapter_receipt_fingerprint_match_count",
                    0,
                )
            ),
            "capture_fingerprint_match_count": _integer(
                source_row.get("dispatch_roundtrip_capture_fingerprint_match_count", 0)
            ),
            "ready": receipt_ready,
            "matches_manifest": _bool(
                source_row.get(
                    "dispatch_roundtrip_adapter_receipt_proof_matches_manifest",
                    False,
                )
            ),
            "matches_runtime_session": _bool(
                source_row.get(
                    "dispatch_roundtrip_adapter_receipt_proof_matches_runtime_session",
                    False,
                )
            ),
        },
        "integrity": {
            "nested_roundtrip_path": str(nested_root),
            "nested_roundtrip_passed": _bool(nested_row.get("passed", False)),
            "manifest_count": int(len(manifest_graph)),
            "manifest_chain_sha256": manifest_chain_sha,
            "fingerprint_count": int(len(fingerprint_inventory)),
            "fingerprint_match_count": int(
                fingerprint_inventory["matches"].map(_bool).sum()
            )
            if not fingerprint_inventory.empty
            else 0,
            "manifest_chain": manifest_chain,
        },
        "provider_profile_sha256": _text(source_row, "dispatch_roundtrip_provider_profile_sha256")
        or _text(source_row, "provider_profile_sha256")
        or _text_value(_mapping(source_config.get("provider_profile")).get("sha256")),
    }
    cycle_id = f"hft-rehearsal-{_canonical_sha256(core)[:24]}"
    payload = {**core, "cycle_id": cycle_id}
    return {
        "schema_version": 1,
        "status": "valid" if valid else "blocked",
        "authorizes_submission": False,
        "digitally_signed": False,
        "cycle_id": cycle_id,
        "certificate_sha256": _canonical_sha256(payload),
        "payload": payload,
    }


def _summary(
    *,
    valid: bool,
    source_root: Path,
    source_row: pd.Series,
    nested_root: Path,
    nested_row: pd.Series,
    checks: pd.DataFrame,
    manifest_graph: pd.DataFrame,
    fingerprint_inventory: pd.DataFrame,
    certificate: dict[str, Any],
) -> pd.DataFrame:
    failed = int((~checks["passed"].astype(bool)).sum()) if not checks.empty else 1
    payload = _mapping(certificate.get("payload"))
    receipts = _mapping(payload.get("provider_receipts"))
    return pd.DataFrame(
        [
            {
                "ready": valid,
                "valid": valid,
                "status": "valid" if valid else "blocked",
                "authorizes_submission": False,
                "digitally_signed": False,
                "cycle_id": certificate.get("cycle_id", ""),
                "certificate_sha256": certificate.get("certificate_sha256", ""),
                "assurance_level": payload.get("assurance_level", ""),
                "source_roundtrip_dir": str(source_root),
                "source_manifest_sha256": _mapping(payload.get("source")).get("manifest_sha256", ""),
                "nested_roundtrip_dir": str(nested_root),
                "source_roundtrip_passed": _bool(source_row.get("passed", False)),
                "nested_roundtrip_passed": _bool(nested_row.get("passed", False)),
                "provider": _text(source_row, "provider"),
                "transport": _text(source_row, "transport"),
                "strategy": _text(source_row, "strategy"),
                "market": _text(source_row, "market"),
                "exchange": _text(source_row, "exchange"),
                "target_mode": _text(source_row, "target_mode"),
                "adapter": _text(source_row, "adapter"),
                "scenario_key": _text(source_row, "scenario_key"),
                "dispatch_orders": _integer(source_row.get("dispatch_orders", 0)),
                "send_requests": _integer(source_row.get("send_requests", 0)),
                "acked_orders": _integer(source_row.get("acked_orders", 0)),
                "missing_request_acks": _integer(source_row.get("missing_request_acks", 0)),
                "rejected_orders": _integer(source_row.get("rejected_orders", 0)),
                "duplicate_ack_orders": _integer(source_row.get("duplicate_ack_orders", 0)),
                "unmatched_acks": _integer(source_row.get("unmatched_acks", 0)),
                "provider_receipts_required": _bool(receipts.get("required", False)),
                "provider_receipt_required_count": _integer(receipts.get("required_count", 0)),
                "provider_receipt_valid_count": _integer(receipts.get("valid_count", 0)),
                "provider_receipt_proof_ready": _bool(receipts.get("ready", False)),
                "manifest_count": int(len(manifest_graph)),
                "manifest_chain_sha256": _mapping(payload.get("integrity")).get(
                    "manifest_chain_sha256", ""
                ),
                "fingerprint_count": int(len(fingerprint_inventory)),
                "fingerprint_match_count": int(
                    fingerprint_inventory["matches"].map(_bool).sum()
                )
                if not fingerprint_inventory.empty
                else 0,
                "failed_checks": failed,
                "failed_check_names": ";".join(
                    checks.loc[~checks["passed"].astype(bool), "check"].astype(str).tolist()
                ),
                "recommendation": "retain_certificate_for_operator_review"
                if valid
                else "repair_broker_rehearsal_before_certification",
                "next_gate": READY_NEXT_GATE if valid else _blocked_next_gate(checks),
                "next_gate_help_command": _help_command(
                    READY_NEXT_GATE if valid else _blocked_next_gate(checks)
                ),
                "primary_action_status": "ready" if valid else "blocked",
            }
        ]
    )


def _action_queue(checks: pd.DataFrame) -> pd.DataFrame:
    if checks.empty:
        return pd.DataFrame(columns=ACTION_QUEUE_COLUMNS)
    rows: list[dict[str, Any]] = []
    for _, check in checks.loc[~checks["passed"].astype(bool)].iterrows():
        name = str(check.get("check", ""))
        gate = _next_gate_for_check(name)
        rows.append(
            {
                "priority": len(rows) + 1,
                "queue_status": "blocked",
                "source": "provider_market_data_imbalance_broker_rehearsal_certificate_checks",
                "component": str(check.get("component", "certificate")),
                "check": name,
                "actual": check.get("value"),
                "operator": check.get("operator"),
                "expected": check.get("threshold"),
                "action": "repair_and_reissue_broker_rehearsal_certificate",
                "reason": str(check.get("reason", "")),
                "recommendation": _recommendation_for_check(name),
                "next_gate": gate,
                "next_gate_help_command": _help_command(gate),
            }
        )
    return pd.DataFrame(rows, columns=ACTION_QUEUE_COLUMNS)


def _summary_with_actions(summary: pd.DataFrame, action_queue: pd.DataFrame) -> pd.DataFrame:
    out = summary.copy()
    out["action_queue_count"] = int(len(action_queue))
    out["blocked_action_count"] = int(
        action_queue.get("queue_status", pd.Series(dtype=str)).astype(str).eq("blocked").sum()
    )
    return out


def _runbook_markdown(
    summary: pd.Series,
    checks: pd.DataFrame,
    action_queue: pd.DataFrame,
) -> str:
    failed = checks.loc[~checks["passed"].astype(bool)] if not checks.empty else checks
    lines = [
        "# Provider Market-Data Imbalance Broker Rehearsal Certificate",
        "",
        f"- Status: **{summary['status']}**",
        f"- Cycle id: `{summary['cycle_id']}`",
        f"- Certificate SHA-256: `{summary['certificate_sha256']}`",
        f"- Assurance level: `{summary['assurance_level']}`",
        "- Authorizes broker submission: **no**",
        "- Digitally signed: **no** (content integrity only)",
        f"- Identity: `{summary['strategy']}` / `{summary['market']}` / `{summary['target_mode']}`",
        f"- Acknowledgements: {int(summary['acked_orders'])}/{int(summary['send_requests'])} accepted",
        f"- Manifest chain: {int(summary['manifest_count'])} manifests, {int(summary['fingerprint_match_count'])}/{int(summary['fingerprint_count'])} fingerprints current",
        f"- Next gate: `{summary['next_gate']}`",
        f"- Next gate help: `{summary['next_gate_help_command']}`",
        "",
        "This artifact certifies only an offline broker rehearsal. It cannot enable, approve, or submit a live order.",
    ]
    if failed.empty:
        lines.extend(
            [
                "",
                "## Operator Review",
                "",
                "Retain the certificate JSON, summary, fingerprint inventory, manifest graph, and manifest together. Reissue after any input, acknowledgement, receipt, configuration, or code-provenance change.",
            ]
        )
    else:
        lines.extend(["", "## Blocking Checks", ""])
        for _, row in failed.iterrows():
            lines.append(
                f"- `{row['check']}`: {row['reason']} (actual `{row['value']}`, expected `{row['threshold']}`)"
            )
    if not action_queue.empty:
        lines.extend(["", "## Action Queue", ""])
        for _, row in action_queue.iterrows():
            lines.append(
                f"- `{row['check']}` -> `{row['next_gate']}`: {row['recommendation']}"
            )
    return "\n".join(lines) + "\n"


def _nested_roundtrip_root(
    source_root: Path,
    source_row: pd.Series,
    source_config: dict[str, Any],
) -> Path:
    summary_path = _text(source_row, "broker_dispatch_roundtrip_dir")
    if summary_path:
        return Path(summary_path).resolve()
    config_summary = _mapping(source_config.get("summary"))
    config_path = _text_value(config_summary.get("broker_dispatch_roundtrip_dir"))
    if config_path:
        return Path(config_path).resolve()
    return (source_root / "broker_dispatch_roundtrip").resolve()


def _strict_check_values(checks: pd.DataFrame) -> dict[str, Any]:
    if checks.empty or "check" not in checks.columns:
        return {}
    return {
        str(row["check"]): row.get("value")
        for _, row in checks.iterrows()
    }


def _all_checks_passed(checks: pd.DataFrame) -> bool:
    return bool(
        not checks.empty
        and "passed" in checks.columns
        and checks["passed"].map(_bool).all()
    )


def _blocked_next_gate(checks: pd.DataFrame) -> str:
    if checks.empty:
        return REPAIR_ROUNDTRIP_GATE
    failed = checks.loc[~checks["passed"].astype(bool)]
    if failed.empty:
        return REPAIR_ROUNDTRIP_GATE
    return _next_gate_for_check(str(failed.iloc[0].get("check", "")))


def _next_gate_for_check(check: str) -> str:
    if "submission" in check or "send_ready" in check or "dry_run" in check:
        return "prepare-provider-market-data-imbalance-broker-dispatch-send"
    if any(token in check for token in ("ack", "rejected", "duplicate", "unmatched")):
        return "reconcile-provider-market-data-imbalance-broker-dispatch"
    if "dispatch_ready" in check or "dispatch_orders" in check:
        return "plan-provider-market-data-imbalance-broker-dispatch"
    return REPAIR_ROUNDTRIP_GATE


def _recommendation_for_check(check: str) -> str:
    if "fingerprint" in check or "manifest" in check or "git_state" in check:
        return "restore immutable inputs and rerun the final provider broker roundtrip from clean code provenance"
    if "receipt" in check:
        return "restore provider receipt and capture proof, then rerun acknowledgement and roundtrip review"
    if "submission" in check or "dry_run" in check:
        return "rebuild the send packet with submission disabled and dry-run-only requests"
    if any(token in check for token in ("ack", "rejected", "duplicate", "unmatched")):
        return "repair acknowledgement reconciliation and rerun the final roundtrip"
    if "identity" in check or "matches" in check:
        return "rebuild the rehearsal from one consistent strategy, market, adapter, and scenario identity"
    return "repair the source proof and reissue the rehearsal certificate"


def _help_command(gate: str) -> str:
    return f"python -m hft_cli {gate} --help" if gate else ""


def _check(
    name: str,
    value: Any,
    operator: str,
    threshold: Any,
    component: str,
    reason: str,
    *,
    required: bool = True,
) -> dict[str, Any]:
    if operator == "is" or operator == "==":
        passed = _scalar_equal(value, threshold)
    elif operator == "in":
        passed = value in threshold
    elif operator == "exists":
        passed = bool(value)
    else:
        passed = False
    return _check_result(
        name,
        value,
        operator,
        threshold,
        passed,
        component,
        reason,
        required=required,
    )


def _check_result(
    name: str,
    value: Any,
    operator: str,
    threshold: Any,
    passed: bool,
    component: str,
    reason: str,
    *,
    required: bool = True,
) -> dict[str, Any]:
    effective_passed = bool(passed or not required)
    return {
        "check": name,
        "component": component,
        "value": value,
        "operator": operator,
        "threshold": threshold,
        "required": required,
        "passed": effective_passed,
        "reason": "" if effective_passed else reason,
    }


def _read_csv(path: Path) -> tuple[pd.DataFrame, str]:
    if not path.is_file():
        return pd.DataFrame(), f"{path.name} does not exist"
    try:
        frame = pd.read_csv(path)
    except (OSError, ValueError, pd.errors.ParserError) as exc:
        return pd.DataFrame(), f"{path.name} is not readable: {exc}"
    if frame.empty:
        return frame, f"{path.name} is empty"
    return frame, ""


def _read_json(path: Path) -> tuple[dict[str, Any], str]:
    if not path.is_file():
        return {}, f"{path.name} does not exist"
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return {}, f"{path.name} is not readable: {exc}"
    if not isinstance(value, dict):
        return {}, f"{path.name} must contain a JSON object"
    return value, ""


def _validate_config(config: ProviderMarketDataImbalanceBrokerRehearsalCertificateConfig) -> None:
    allowed = tuple(_identity(value) for value in config.allowed_target_modes if _identity(value))
    if not allowed:
        raise ValueError("allowed_target_modes must contain at least one mode")
    if any(value not in SAFE_TARGET_MODES for value in allowed):
        raise ValueError(f"allowed_target_modes must be a subset of {SAFE_TARGET_MODES}")
    if config.max_manifest_count < 1:
        raise ValueError("max_manifest_count must be at least 1")


def _validate_output_location(source_root: Path, output_dir: Path) -> None:
    if source_root == output_dir or source_root in output_dir.parents:
        raise ValueError("certificate output_dir must be outside the source roundtrip directory")


def _canonical_sha256(value: Any) -> str:
    encoded = json.dumps(
        _jsonable(value),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _scalar_equal(left: Any, right: Any) -> bool:
    if isinstance(right, bool):
        return _bool(left) is right
    if isinstance(right, (int, float)) and not isinstance(right, bool):
        try:
            return float(left) == float(right)
        except (TypeError, ValueError):
            return False
    if isinstance(right, list):
        return left in right
    return _text_value(left) == _text_value(right)


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _text(row: pd.Series, field: str) -> str:
    return _text_value(row.get(field, "")) if not row.empty else ""


def _text_value(value: Any) -> str:
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except (TypeError, ValueError):
        pass
    return str(value).strip()


def _identity(value: Any) -> str:
    return _text_value(value).lower()


def _bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    text = _text_value(value).lower()
    if text in {"true", "1", "yes", "y", "on"}:
        return True
    if text in {"false", "0", "no", "n", "off", "", "nan", "none"}:
        return False
    return bool(value)


def _integer(value: Any) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return 0


def _jsonable(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_jsonable(item) for item in value]
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, pd.Series):
        return {str(key): _jsonable(item) for key, item in value.to_dict().items()}
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
