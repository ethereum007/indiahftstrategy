from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path

import pandas as pd

from data.instruments import parse_option_instrument_id
from reports.manifest import write_experiment_manifest


@dataclass(frozen=True)
class InstrumentMetadataConfig:
    instrument_column: str = "instrument_id"
    min_parse_coverage: float = 1.0


@dataclass(frozen=True)
class InstrumentMetadataReport:
    metadata: pd.DataFrame
    gaps: pd.DataFrame
    summary: pd.DataFrame
    output_dir: Path | None = None

    @property
    def passed(self) -> bool:
        if self.summary.empty:
            return False
        return bool(self.summary.iloc[0]["passed"])


def build_instrument_metadata_report(
    frame: pd.DataFrame,
    *,
    config: InstrumentMetadataConfig | None = None,
) -> InstrumentMetadataReport:
    config = config or InstrumentMetadataConfig()
    _validate_config(config)
    if config.instrument_column not in frame.columns:
        raise ValueError(f"input missing instrument column: {config.instrument_column}")
    metadata = _metadata(frame[config.instrument_column])
    gaps = metadata.loc[~metadata["parsed"].astype(bool), ["instrument_id", "reason"]].reset_index(drop=True)
    summary = _summary(metadata, gaps, config)
    return InstrumentMetadataReport(metadata=metadata, gaps=gaps, summary=summary)


def write_instrument_metadata_report(
    input_path: str | Path,
    *,
    output_dir: str | Path,
    config: InstrumentMetadataConfig | None = None,
) -> InstrumentMetadataReport:
    config = config or InstrumentMetadataConfig()
    path = Path(input_path)
    if not path.exists():
        raise FileNotFoundError(f"instrument metadata input not found: {path}")
    report = build_instrument_metadata_report(pd.read_csv(path), config=config)
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    report.metadata.to_csv(out / "instrument_metadata.csv", index=False)
    report.gaps.to_csv(out / "instrument_metadata_gaps.csv", index=False)
    report.summary.to_csv(out / "instrument_metadata_summary.csv", index=False)
    write_experiment_manifest(
        out,
        run_type="instrument_metadata_report",
        parameters={"config": asdict(config)},
        inputs={"input": path},
    )
    return InstrumentMetadataReport(report.metadata, report.gaps, report.summary, out)


def _metadata(instruments: pd.Series) -> pd.DataFrame:
    rows = []
    for raw in instruments.astype(str):
        text = raw.strip()
        parsed = parse_option_instrument_id(text)
        rows.append(
            {
                "instrument_id": text,
                "parsed": parsed is not None,
                "underlying": parsed.underlying if parsed is not None else "",
                "expiry": parsed.expiry if parsed is not None else "",
                "strike": parsed.strike if parsed is not None else pd.NA,
                "option_type": parsed.option_type if parsed is not None else "",
                "symbol_format": parsed.symbol_format if parsed is not None else "unknown",
                "reason": "" if parsed is not None else "unsupported_option_symbol_format",
            }
        )
    return pd.DataFrame(rows).drop_duplicates(subset=["instrument_id"]).reset_index(drop=True)


def _summary(
    metadata: pd.DataFrame,
    gaps: pd.DataFrame,
    config: InstrumentMetadataConfig,
) -> pd.DataFrame:
    total = int(len(metadata))
    parsed = int(metadata["parsed"].astype(bool).sum()) if total else 0
    coverage = parsed / total if total else 1.0
    format_counts = (
        metadata.loc[metadata["parsed"].astype(bool), "symbol_format"].value_counts().to_dict()
        if total
        else {}
    )
    return pd.DataFrame(
        [
            {
                "passed": bool(coverage >= config.min_parse_coverage),
                "instruments": total,
                "parsed_instruments": parsed,
                "unparsed_instruments": int(len(gaps)),
                "parse_coverage": float(coverage),
                "min_parse_coverage": float(config.min_parse_coverage),
                "symbol_formats": "|".join(f"{key}:{value}" for key, value in sorted(format_counts.items())),
            }
        ]
    )


def _validate_config(config: InstrumentMetadataConfig) -> None:
    if not str(config.instrument_column).strip():
        raise ValueError("instrument_column must not be blank")
    if not 0 <= config.min_parse_coverage <= 1:
        raise ValueError("min_parse_coverage must be between 0 and 1")
