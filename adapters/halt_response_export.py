from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from adapters.broker import adapter_schema_status, get_adapter
from adapters.mapped_order_export import MAPPING_COLUMNS, MappedOrderExportConfig, map_broker_orders
from reports.manifest import write_experiment_manifest


@dataclass(frozen=True)
class HaltResponseExportConfig:
    adapter: str = "normalized"
    cancel_output_filename: str = "broker_cancel_orders.csv"
    flatten_output_filename: str = "broker_flatten_orders.csv"
    require_response_ready: bool = True
    require_all_mapped: bool = True


@dataclass(frozen=True)
class HaltResponseExportReport:
    cancel_orders: pd.DataFrame
    flatten_orders: pd.DataFrame
    checks: pd.DataFrame
    summary: pd.DataFrame
    schema: pd.DataFrame
    output_dir: Path | None = None

    @property
    def ready(self) -> bool:
        return bool(self.summary.iloc[0]["ready"]) if not self.summary.empty else False


def export_halt_response_actions(
    halt_summary: pd.DataFrame,
    cancel_actions: pd.DataFrame,
    flatten_actions: pd.DataFrame,
    *,
    cancel_mapping: pd.DataFrame | None = None,
    flatten_mapping: pd.DataFrame | None = None,
    config: HaltResponseExportConfig | None = None,
) -> HaltResponseExportReport:
    config = config or HaltResponseExportConfig()
    _validate_config(config)
    _require_summary(halt_summary)
    cancel_actions = cancel_actions.copy().reset_index(drop=True)
    flatten_actions = flatten_actions.copy().reset_index(drop=True)
    cancel_orders, cancel_checks, cancel_schema = _export_action_frame(
        cancel_actions,
        cancel_mapping,
        action_type="cancel",
        output_filename=config.cancel_output_filename,
        config=config,
    )
    flatten_orders, flatten_checks, flatten_schema = _export_action_frame(
        flatten_actions,
        flatten_mapping,
        action_type="flatten",
        output_filename=config.flatten_output_filename,
        config=config,
    )
    checks = pd.concat(
        [
            _response_checks(halt_summary.iloc[0], config),
            cancel_checks,
            flatten_checks,
        ],
        ignore_index=True,
    )
    schema = pd.concat([cancel_schema, flatten_schema], ignore_index=True)
    summary = _summary(halt_summary.iloc[0], cancel_orders, flatten_orders, checks, config)
    return HaltResponseExportReport(
        cancel_orders=cancel_orders,
        flatten_orders=flatten_orders,
        checks=checks,
        summary=summary,
        schema=schema,
    )


def write_halt_response_export(
    *,
    halt_response_dir: str | Path,
    output_dir: str | Path,
    cancel_mapping_path: str | Path | None = None,
    flatten_mapping_path: str | Path | None = None,
    config: HaltResponseExportConfig | None = None,
) -> HaltResponseExportReport:
    config = config or HaltResponseExportConfig()
    _validate_config(config)
    halt_dir = Path(halt_response_dir)
    halt_summary_path = halt_dir / "halt_response_summary.csv"
    cancel_path = halt_dir / "halt_cancel_orders.csv"
    flatten_path = halt_dir / "halt_flatten_orders.csv"
    if not halt_summary_path.exists():
        raise FileNotFoundError(f"halt response summary not found: {halt_summary_path}")
    if not cancel_path.exists():
        raise FileNotFoundError(f"halt cancel orders not found: {cancel_path}")
    if not flatten_path.exists():
        raise FileNotFoundError(f"halt flatten orders not found: {flatten_path}")

    cancel_mapping = _read_mapping(cancel_mapping_path)
    flatten_mapping = _read_mapping(flatten_mapping_path)
    report = export_halt_response_actions(
        pd.read_csv(halt_summary_path),
        pd.read_csv(cancel_path),
        pd.read_csv(flatten_path),
        cancel_mapping=cancel_mapping,
        flatten_mapping=flatten_mapping,
        config=config,
    )
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    report.cancel_orders.to_csv(out / config.cancel_output_filename, index=False)
    report.flatten_orders.to_csv(out / config.flatten_output_filename, index=False)
    report.checks.to_csv(out / "halt_response_export_checks.csv", index=False)
    report.summary.to_csv(out / "halt_response_export_summary.csv", index=False)
    report.schema.to_csv(out / "halt_response_export_schema.csv", index=False)
    inputs: dict[str, Any] = {
        "halt_response_summary": halt_summary_path,
        "halt_cancel_orders": cancel_path,
        "halt_flatten_orders": flatten_path,
    }
    if cancel_mapping_path is not None:
        inputs["cancel_mapping"] = Path(cancel_mapping_path)
    if flatten_mapping_path is not None:
        inputs["flatten_mapping"] = Path(flatten_mapping_path)
    write_experiment_manifest(
        out,
        run_type="halt_response_export",
        parameters={"config": asdict(config)},
        inputs=inputs,
    )
    return HaltResponseExportReport(
        report.cancel_orders,
        report.flatten_orders,
        report.checks,
        report.summary,
        report.schema,
        out,
    )


def _export_action_frame(
    actions: pd.DataFrame,
    mapping: pd.DataFrame | None,
    *,
    action_type: str,
    output_filename: str,
    config: HaltResponseExportConfig,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    if mapping is None:
        return _passthrough_action_frame(actions, action_type=action_type, output_filename=output_filename, config=config)
    targets = _mapping_target_columns(mapping)
    if actions.empty:
        mapped = pd.DataFrame(columns=targets)
        checks = _empty_mapping_checks(mapping, action_type=action_type, output_filename=output_filename)
        schema = _schema_frame(mapped, mapping, action_type=action_type, output_filename=output_filename, config=config)
        return mapped, checks, schema

    mapped = map_broker_orders(
        actions,
        mapping,
        config=MappedOrderExportConfig(
            adapter=config.adapter,
            output_filename=output_filename,
            require_all_mapped=config.require_all_mapped,
        ),
    )
    checks = mapped.checks.copy()
    checks.insert(0, "action_type", action_type)
    checks.insert(1, "output_file", output_filename)
    schema = mapped.schema.copy()
    schema.insert(0, "action_type", action_type)
    schema.insert(1, "output_file", output_filename)
    return mapped.orders, checks, schema


def _passthrough_action_frame(
    actions: pd.DataFrame,
    *,
    action_type: str,
    output_filename: str,
    config: HaltResponseExportConfig,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    out = actions.copy().reset_index(drop=True)
    checks = pd.DataFrame(
        [
            {
                "action_type": action_type,
                "output_file": output_filename,
                "target_column": "*",
                "source_column": "*",
                "default_value": "",
                "required": True,
                "transform": "passthrough",
                "source_present": True,
                "default_present": False,
                "values_present": True,
                "passed": True,
                "reason": "",
            }
        ]
    )
    schema = pd.DataFrame(
        [
            {
                "action_type": action_type,
                "output_file": output_filename,
                "adapter": config.adapter,
                "adapter_schema_status": adapter_schema_status(config.adapter),
                "target_column": column,
                "source_column": column,
                "default_value": "",
                "required": True,
                "transform": "passthrough",
                "dtype": str(out[column].dtype),
            }
            for column in out.columns
        ]
    )
    return out, checks, schema


def _response_checks(row: pd.Series, config: HaltResponseExportConfig) -> pd.DataFrame:
    response_ready = _to_bool(row.get("ready", False))
    halt_adapter = str(row.get("adapter", "")).strip()
    adapter_consistent = not halt_adapter or config.adapter in {"normalized", halt_adapter}
    return pd.DataFrame(
        [
            _check(
                "response_ready",
                response_ready,
                "is",
                True,
                response_ready or not config.require_response_ready,
                "halt response plan is not ready",
            ),
            _check(
                "adapter_consistent",
                config.adapter,
                "matches",
                halt_adapter or config.adapter,
                adapter_consistent,
                "export adapter does not match halt response adapter",
            ),
        ]
    )


def _summary(
    halt_row: pd.Series,
    cancel_orders: pd.DataFrame,
    flatten_orders: pd.DataFrame,
    checks: pd.DataFrame,
    config: HaltResponseExportConfig,
) -> pd.DataFrame:
    failed_rows = _failed_check_rows(checks)
    primary_blocker = _first_failed_check(failed_rows)
    failed = int(len(failed_rows)) if not checks.empty else 1
    ready = failed == 0
    return pd.DataFrame(
        [
            {
                "ready": ready,
                "adapter": config.adapter,
                "adapter_schema_status": adapter_schema_status(config.adapter),
                "scenario_key": str(halt_row.get("scenario_key", "")),
                "cancel_orders": int(len(cancel_orders)),
                "flatten_orders": int(len(flatten_orders)),
                "failed_checks": failed,
                "failed_check_count": failed,
                "failed_check_names": _failed_check_names(failed_rows),
                "first_failed_reason": _check_reason(primary_blocker),
                "primary_blocker_check": _check_name(primary_blocker),
                "primary_blocker_value": _check_value(primary_blocker, "value"),
                "primary_blocker_operator": _check_value(primary_blocker, "operator")
                or _check_value(primary_blocker, "transform"),
                "primary_blocker_threshold": _check_value(primary_blocker, "threshold"),
                "primary_blocker_reason": _check_reason(primary_blocker),
                "cancel_output_file": config.cancel_output_filename,
                "flatten_output_file": config.flatten_output_filename,
                "recommendation": "send_halt_actions_to_broker" if ready else "fix_halt_action_export",
            }
        ]
    )


def _failed_check_rows(checks: pd.DataFrame) -> pd.DataFrame:
    if checks.empty or "passed" not in checks.columns:
        return checks.iloc[:0].copy()
    return checks.loc[~checks["passed"].map(_to_bool)].copy().reset_index(drop=True)


def _first_failed_check(failed_rows: pd.DataFrame) -> pd.Series:
    if failed_rows.empty:
        return pd.Series(dtype=object)
    return failed_rows.iloc[0]


def _failed_check_names(failed_rows: pd.DataFrame) -> str:
    names = [_check_name(row) for _, row in failed_rows.iterrows()]
    return ";".join(name for name in names if name)


def _check_name(row: pd.Series) -> str:
    if row.empty:
        return ""
    explicit = _check_value(row, "check")
    target = explicit or _check_value(row, "target_column")
    action_type = _check_value(row, "action_type")
    output_file = _check_value(row, "output_file")
    pieces = [piece for piece in (action_type, output_file, target) if piece and piece != "*"]
    return ":".join(pieces)


def _check_reason(row: pd.Series) -> str:
    return _check_value(row, "reason")


def _check_value(row: pd.Series, column: str) -> str:
    if row.empty or column not in row.index:
        return ""
    return _clean(row[column])


def _schema_frame(
    mapped: pd.DataFrame,
    mapping: pd.DataFrame,
    *,
    action_type: str,
    output_filename: str,
    config: HaltResponseExportConfig,
) -> pd.DataFrame:
    rows = []
    frame = mapping.copy()
    for column in MAPPING_COLUMNS:
        if column not in frame.columns:
            frame[column] = ""
    for row in frame.itertuples(index=False):
        target = _clean(getattr(row, "target_column"))
        if not target:
            continue
        rows.append(
            {
                "action_type": action_type,
                "output_file": output_filename,
                "adapter": config.adapter,
                "adapter_schema_status": adapter_schema_status(config.adapter),
                "target_column": target,
                "source_column": _clean(getattr(row, "source_column")),
                "default_value": _clean(getattr(row, "default_value")),
                "required": _to_bool(getattr(row, "required"), default=True),
                "transform": _clean(getattr(row, "transform")) or "identity",
                "dtype": str(mapped[target].dtype) if target in mapped.columns else "object",
            }
        )
    return pd.DataFrame(rows)


def _empty_mapping_checks(mapping: pd.DataFrame, *, action_type: str, output_filename: str) -> pd.DataFrame:
    rows = []
    frame = mapping.copy()
    for column in MAPPING_COLUMNS:
        if column not in frame.columns:
            frame[column] = ""
    for row in frame.itertuples(index=False):
        rows.append(
            {
                "action_type": action_type,
                "output_file": output_filename,
                "target_column": _clean(getattr(row, "target_column")),
                "source_column": _clean(getattr(row, "source_column")),
                "default_value": _clean(getattr(row, "default_value")),
                "required": _to_bool(getattr(row, "required"), default=True),
                "transform": _clean(getattr(row, "transform")) or "identity",
                "source_present": True,
                "default_present": False,
                "values_present": True,
                "passed": True,
                "reason": "",
            }
        )
    return pd.DataFrame(rows)


def _mapping_target_columns(mapping: pd.DataFrame) -> list[str]:
    if mapping.empty:
        raise ValueError("halt action mapping is empty")
    if "target_column" not in mapping.columns:
        raise ValueError("halt action mapping missing required column: target_column")
    targets = [_clean(value) for value in mapping["target_column"] if _clean(value)]
    if len(targets) != len(set(targets)):
        duplicates = sorted({target for target in targets if targets.count(target) > 1})
        raise ValueError(f"halt action mapping has duplicate target columns: {duplicates}")
    return targets


def _read_mapping(path: str | Path | None) -> pd.DataFrame | None:
    if path is None:
        return None
    mapping_path = Path(path)
    if not mapping_path.exists():
        raise FileNotFoundError(f"halt action mapping not found: {mapping_path}")
    return pd.read_csv(mapping_path)


def _require_summary(summary: pd.DataFrame) -> None:
    if summary.empty:
        raise ValueError("halt response summary is empty")
    missing = [column for column in ("ready",) if column not in summary.columns]
    if missing:
        raise ValueError(f"halt response summary missing columns: {missing}")


def _validate_config(config: HaltResponseExportConfig) -> None:
    get_adapter(config.adapter)
    for name in (config.cancel_output_filename, config.flatten_output_filename):
        output_name = Path(name)
        if not name or output_name.name != name:
            raise ValueError("halt action output filenames must be file names without directories")


def _check(
    name: str,
    value: object,
    operator: str,
    threshold: object,
    passed: bool,
    reason: str,
) -> dict[str, object]:
    return {
        "action_type": "response",
        "output_file": "",
        "target_column": name,
        "source_column": "",
        "default_value": "",
        "required": True,
        "transform": operator,
        "source_present": True,
        "default_present": False,
        "values_present": True,
        "passed": bool(passed),
        "reason": "" if passed else reason,
        "value": value,
        "threshold": threshold,
    }


def _to_bool(value: object, *, default: bool = False) -> bool:
    if pd.isna(value):
        return default
    if isinstance(value, str):
        normalized = value.strip().lower()
        if not normalized:
            return default
        return normalized in {"1", "true", "yes", "y"}
    return bool(value)


def _clean(value: object) -> str:
    if pd.isna(value):
        return ""
    return str(value).strip()
