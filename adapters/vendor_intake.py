from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from adapters.broker import adapter_schema_status, get_adapter
from adapters.schema_audit import SCHEMA_KIND_ATTRS
from reports.manifest import write_experiment_manifest


AUTO_KINDS = ("ticks", "chain", "orders", "fills")


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
    output_dir: Path | None = None

    @property
    def ready(self) -> bool:
        if self.summary.empty:
            return False
        return bool(self.summary.iloc[0]["ready"])


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
        config=config,
    )
    return VendorCsvIntakeReport(
        columns=columns,
        kind_scores=kind_scores,
        mapping_candidates=candidates,
        mapping_draft=mapping_draft,
        summary=summary,
    )


def write_vendor_csv_intake_report(
    sample_path: str | Path,
    *,
    output_dir: str | Path,
    config: VendorCsvIntakeConfig | None = None,
) -> VendorCsvIntakeReport:
    config = config or VendorCsvIntakeConfig()
    _validate_config(config)
    sample_file = Path(sample_path)
    if not sample_file.exists():
        raise FileNotFoundError(f"vendor CSV sample not found: {sample_file}")
    sample = pd.read_csv(sample_file, nrows=config.sample_rows)
    report = profile_vendor_csv(sample, sample_path=sample_file, config=config)

    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    report.columns.to_csv(out / "vendor_intake_columns.csv", index=False)
    report.kind_scores.to_csv(out / "vendor_intake_kind_scores.csv", index=False)
    report.mapping_candidates.to_csv(out / "vendor_intake_mapping_candidates.csv", index=False)
    report.mapping_draft.to_csv(out / config.output_mapping_file, index=False)
    report.summary.to_csv(out / "vendor_intake_summary.csv", index=False)
    write_experiment_manifest(
        out,
        run_type="vendor_csv_intake",
        parameters={"config": asdict(config)},
        inputs={"sample": sample_file},
    )
    return VendorCsvIntakeReport(
        columns=report.columns,
        kind_scores=report.kind_scores,
        mapping_candidates=report.mapping_candidates,
        mapping_draft=report.mapping_draft,
        summary=report.summary,
        output_dir=out,
    )


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
        ["ready", "mapping_coverage", "mapped_columns", "exact_columns", "kind"],
        ascending=[False, False, False, False, True],
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
    config: VendorCsvIntakeConfig,
) -> pd.DataFrame:
    best = kind_scores.iloc[0]
    unmapped = int(best["unmapped_required_columns"])
    ready = bool(best["ready"])
    return pd.DataFrame(
        [
            {
                "ready": ready,
                "adapter": config.adapter,
                "adapter_schema_status": adapter_schema_status(config.adapter),
                "requested_kind": config.kind,
                "best_kind": str(best["kind"]),
                "source_path": source_path,
                "sampled_rows": int(len(sample)),
                "source_columns": int(len(columns)),
                "required_columns": int(best["required_columns"]),
                "mapped_columns": int(best["mapped_columns"]),
                "unmapped_required_columns": unmapped,
                "mapping_coverage": float(best["mapping_coverage"]),
                "min_mapping_coverage": float(config.min_mapping_coverage),
                "output_mapping_file": config.output_mapping_file,
                "recommendation": "review_mapping_then_normalize" if ready else "complete_vendor_mapping_before_research",
                "unmapped_normalized_columns": ";".join(
                    mapping_draft.loc[
                        mapping_draft["source_column"].astype(str) == "",
                        "normalized_column",
                    ].astype(str)
                ),
            }
        ]
    )


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


def _validate_config(config: VendorCsvIntakeConfig) -> None:
    get_adapter(config.adapter)
    _candidate_kinds(config.kind)
    if config.sample_rows <= 0:
        raise ValueError("sample_rows must be positive")
    if not 0 <= config.min_mapping_coverage <= 1:
        raise ValueError("min_mapping_coverage must be between 0 and 1")
    if not config.output_mapping_file:
        raise ValueError("output_mapping_file is required")
