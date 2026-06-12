from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from adapters.broker import get_adapter
from adapters.schema_audit import SCHEMA_KIND_ATTRS
from data.chains import normalize_option_chain
from data.loaders import _to_ns, normalize_ticks
from markets.profiles import INDIA_NSE_INDEX_DERIVATIVES
from reports.manifest import write_experiment_manifest


@dataclass(frozen=True)
class MappedDataConfig:
    adapter: str = "normalized"
    kind: str = "ticks"
    output_filename: str = "normalized_data.csv"
    timestamp_unit: str = "ns"
    timestamp_tz: str | None = None
    filter_session: bool = True
    market: str = INDIA_NSE_INDEX_DERIVATIVES.name
    require_all_mapped: bool = True


@dataclass(frozen=True)
class MappedDataReport:
    data: pd.DataFrame
    checks: pd.DataFrame
    summary: pd.DataFrame
    output_dir: Path | None = None

    @property
    def ready(self) -> bool:
        if self.summary.empty:
            return False
        return bool(self.summary.iloc[0]["ready"])


def normalize_mapped_data(
    raw: pd.DataFrame,
    mapping: pd.DataFrame,
    *,
    config: MappedDataConfig | None = None,
) -> MappedDataReport:
    config = config or MappedDataConfig()
    canonical_kind, expected_columns = _expected_columns(config)
    rows = _mapping_rows(mapping, expected_columns)
    mapped_columns: dict[str, pd.Series] = {}
    checks = []
    for row in rows:
        values, check = _map_column(raw, row, require_all_mapped=config.require_all_mapped)
        mapped_columns[row["normalized_column"]] = values
        checks.append(check)

    checks_frame = pd.DataFrame(checks)
    mapped = pd.DataFrame(mapped_columns)
    if checks_frame.empty or not bool(checks_frame["passed"].astype(bool).all()):
        data = mapped.iloc[0:0].copy()
        summary = _summary(raw, data, checks_frame, config, canonical_kind)
        return MappedDataReport(data=data, checks=checks_frame, summary=summary)

    data = _normalize_kind(mapped, canonical_kind, config)
    summary = _summary(raw, data, checks_frame, config, canonical_kind)
    return MappedDataReport(data=data, checks=checks_frame, summary=summary)


def write_mapped_data_normalization(
    input_path: str | Path,
    mapping_path: str | Path,
    *,
    output_dir: str | Path,
    config: MappedDataConfig | None = None,
) -> MappedDataReport:
    config = config or MappedDataConfig()
    _validate_config(config)
    input_file = Path(input_path)
    mapping_file = Path(mapping_path)
    if not input_file.exists():
        raise FileNotFoundError(f"mapped data input not found: {input_file}")
    if not mapping_file.exists():
        raise FileNotFoundError(f"mapped data mapping not found: {mapping_file}")
    raw = pd.read_csv(input_file)
    mapping = pd.read_csv(mapping_file)
    report = normalize_mapped_data(raw, mapping, config=config)

    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    report.data.to_csv(out / config.output_filename, index=False)
    report.checks.to_csv(out / "mapped_data_checks.csv", index=False)
    report.summary.to_csv(out / "mapped_data_summary.csv", index=False)
    write_experiment_manifest(
        out,
        run_type="mapped_data_normalization",
        parameters={"config": asdict(config)},
        inputs={"input": input_file, "mapping": mapping_file},
    )
    return MappedDataReport(report.data, report.checks, report.summary, out)


def _expected_columns(config: MappedDataConfig) -> tuple[str, list[str]]:
    _validate_config(config)
    canonical_kind, attr = _schema_kind(config.kind)
    spec = get_adapter(config.adapter)
    return canonical_kind, [str(column) for column in getattr(spec, attr).keys()]


def _mapping_rows(mapping: pd.DataFrame, expected_columns: list[str]) -> list[dict[str, Any]]:
    if mapping.empty:
        raise ValueError("mapped data mapping is empty")
    target_field = _target_field(mapping)
    frame = mapping.copy()
    for column in ("source_column", "default_value", "required", "transform"):
        if column not in frame.columns:
            frame[column] = ""

    by_target: dict[str, dict[str, Any]] = {}
    for index, row in frame.iterrows():
        target = _cell(row, target_field)
        if not target:
            raise ValueError(f"mapped data mapping row {index} has blank normalized column")
        if target in by_target:
            raise ValueError(f"mapped data mapping has duplicate normalized column: {target}")
        by_target[target] = {
            "normalized_column": target,
            "source_column": _cell(row, "source_column"),
            "default_value": _cell(row, "default_value"),
            "required": _to_bool(row.get("required", True), default=True),
            "transform": _cell(row, "transform").lower() or "identity",
        }

    unknown = sorted(target for target in by_target if target not in expected_columns)
    if unknown:
        raise ValueError(f"mapped data mapping has unknown normalized columns: {unknown}")

    rows = []
    for column in expected_columns:
        rows.append(
            by_target.get(
                column,
                {
                    "normalized_column": column,
                    "source_column": "",
                    "default_value": "",
                    "required": True,
                    "transform": "identity",
                },
            )
        )
    return rows


def _target_field(mapping: pd.DataFrame) -> str:
    if "normalized_column" in mapping.columns:
        return "normalized_column"
    if "target_column" in mapping.columns:
        return "target_column"
    raise ValueError("mapped data mapping missing required column: normalized_column")


def _map_column(
    raw: pd.DataFrame,
    row: dict[str, Any],
    *,
    require_all_mapped: bool,
) -> tuple[pd.Series, dict[str, Any]]:
    source_column = str(row["source_column"])
    default_value = str(row["default_value"])
    source_present = bool(source_column and source_column in raw.columns)
    default_present = bool(default_value)
    if source_present:
        values = raw[source_column].copy()
    else:
        values = pd.Series([pd.NA] * len(raw), index=raw.index)
    if default_present:
        values = values.mask(~_nonempty_mask(values), default_value)
    values = _apply_transform(values, str(row["transform"]))
    values_present = bool(_nonempty_mask(values).all()) if len(values) else False
    required = bool(row["required"])
    passed = (not required) or (not require_all_mapped) or ((source_present or default_present) and values_present)
    reason = ""
    if not passed:
        if not source_present and not default_present:
            reason = "required normalized column has no available source column or default value"
        else:
            reason = "required normalized column has blank mapped values"
    check = {
        "normalized_column": row["normalized_column"],
        "source_column": source_column,
        "default_value": default_value,
        "required": required,
        "transform": row["transform"],
        "source_present": source_present,
        "default_present": default_present,
        "values_present": values_present,
        "passed": bool(passed),
        "reason": reason,
    }
    return values.reset_index(drop=True), check


def _normalize_kind(mapped: pd.DataFrame, canonical_kind: str, config: MappedDataConfig) -> pd.DataFrame:
    if canonical_kind == "ticks":
        return normalize_ticks(
            mapped,
            timestamp_unit=config.timestamp_unit,
            timestamp_tz=config.timestamp_tz,
            filter_session=config.filter_session,
            market=config.market,
        ).data
    if canonical_kind == "chain":
        return normalize_option_chain(
            mapped,
            timestamp_unit=config.timestamp_unit,
            timestamp_tz=config.timestamp_tz,
            filter_session=config.filter_session,
            market=config.market,
        ).data
    if canonical_kind == "orders":
        return _normalize_order_like(mapped, ts_column="ts_sent_ns", required_name="orders", config=config)
    if canonical_kind == "fills":
        return _normalize_order_like(mapped, ts_column="ts_fill_ns", required_name="fills", config=config)
    raise ValueError(f"unsupported mapped data kind {canonical_kind!r}")


def _normalize_order_like(
    mapped: pd.DataFrame,
    *,
    ts_column: str,
    required_name: str,
    config: MappedDataConfig,
) -> pd.DataFrame:
    required = ["client_order_id", "instrument_id", ts_column, "side", "qty", "price"]
    missing = [column for column in required if column not in mapped.columns]
    if missing:
        raise ValueError(f"{required_name} missing required normalized columns: {missing}")
    out = mapped[required].copy()
    out[ts_column] = _to_ns(out[ts_column], unit=config.timestamp_unit, timestamp_tz=config.timestamp_tz)
    out["side"] = out["side"].map(_side_signed).astype("Int64")
    out["qty"] = pd.to_numeric(out["qty"], errors="coerce").astype("Int64")
    out["price"] = pd.to_numeric(out["price"], errors="coerce")
    null_mask = out[required].isna().any(axis=1)
    out = out.loc[~null_mask].copy()
    out = out.sort_values(ts_column, kind="mergesort").reset_index(drop=True)
    return out


def _summary(
    raw: pd.DataFrame,
    data: pd.DataFrame,
    checks: pd.DataFrame,
    config: MappedDataConfig,
    canonical_kind: str,
) -> pd.DataFrame:
    failed = int((~checks["passed"].astype(bool)).sum()) if not checks.empty else 0
    mapped_columns = int(checks["source_present"].astype(bool).sum()) if not checks.empty else 0
    defaulted_columns = int(checks["default_present"].astype(bool).sum()) if not checks.empty else 0
    return pd.DataFrame(
        [
            {
                "ready": bool(failed == 0 and len(data) > 0),
                "adapter": config.adapter,
                "kind": canonical_kind,
                "input_rows": int(len(raw)),
                "output_rows": int(len(data)),
                "required_columns": int(checks["required"].astype(bool).sum()) if not checks.empty else 0,
                "mapped_columns": mapped_columns,
                "defaulted_columns": defaulted_columns,
                "failed_mappings": failed,
                "output_file": config.output_filename,
            }
        ]
    )


def _apply_transform(values: pd.Series, transform: str) -> pd.Series:
    key = transform.strip().lower().replace("-", "_")
    if key in {"", "identity", "none"}:
        return values
    if key == "string":
        return values.astype("string")
    if key == "uppercase":
        return values.astype("string").str.upper()
    if key == "lowercase":
        return values.astype("string").str.lower()
    if key == "int":
        return pd.to_numeric(values, errors="coerce").astype("Int64")
    if key == "float":
        return pd.to_numeric(values, errors="coerce")
    if key == "side_text":
        return values.map(_side_text).astype("string")
    if key == "side_signed":
        return values.map(_side_signed).astype("Int64")
    raise ValueError(f"unknown mapped data transform {transform!r}")


def _side_text(value: object) -> object:
    side = _side_signed(value)
    if pd.isna(side):
        return pd.NA
    return "BUY" if int(side) > 0 else "SELL"


def _side_signed(value: object) -> object:
    if pd.isna(value):
        return pd.NA
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "+1", "b", "buy", "bid"}:
            return 1
        if normalized in {"-1", "s", "sell", "ask"}:
            return -1
        return pd.NA
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return pd.NA
    if numeric > 0:
        return 1
    if numeric < 0:
        return -1
    return pd.NA


def _schema_kind(kind: str) -> tuple[str, str]:
    key = kind.strip().lower().replace("-", "_")
    try:
        return SCHEMA_KIND_ATTRS[key]
    except KeyError as exc:
        raise ValueError(f"unknown mapped data kind {kind!r}; known kinds: {sorted(SCHEMA_KIND_ATTRS)}") from exc


def _validate_config(config: MappedDataConfig) -> None:
    get_adapter(config.adapter)
    _schema_kind(config.kind)
    output_name = Path(config.output_filename)
    if not config.output_filename or output_name.name != config.output_filename:
        raise ValueError("output_filename must be a file name without directories")


def _cell(row: pd.Series, column: str) -> str:
    value = row.get(column, "")
    if pd.isna(value):
        return ""
    return str(value).strip()


def _to_bool(value: object, *, default: bool) -> bool:
    if pd.isna(value):
        return default
    if isinstance(value, str):
        normalized = value.strip().lower()
        if not normalized:
            return default
        return normalized in {"1", "true", "yes", "y"}
    return bool(value)


def _nonempty_mask(values: pd.Series) -> pd.Series:
    return values.notna() & values.astype("string").str.strip().ne("").fillna(False)
