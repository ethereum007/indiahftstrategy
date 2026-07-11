from __future__ import annotations

from pathlib import Path

import pandas as pd

from reports.manifest import file_sha256, verify_experiment_manifest


def build_sweep_provenance(
    sweep_paths: list[str | Path],
    labels: list[str] | None = None,
    *,
    roles: list[str] | None = None,
) -> pd.DataFrame:
    paths = [Path(path).resolve() for path in sweep_paths]
    if labels is not None and len(labels) != len(paths):
        raise ValueError("labels must match sweep_paths length")
    if roles is not None and len(roles) != len(paths):
        raise ValueError("roles must match sweep_paths length")
    resolved_labels = labels or [path.stem for path in paths]
    resolved_roles = roles or ["research"] * len(paths)
    rows: list[dict[str, object]] = []
    for label, role, path in zip(resolved_labels, resolved_roles, paths):
        target = sweep_runs_path(path)
        manifest_path = sweep_manifest_path(path)
        try:
            required_artifact = target.resolve().relative_to(
                manifest_path.parent.resolve()
            ).as_posix()
        except ValueError:
            required_artifact = f"outside_manifest_root/{target.name}"
        integrity = verify_experiment_manifest(
            manifest_path,
            required_artifacts=(required_artifact,),
            require_input_fingerprints=True,
        )
        rows.append(
            {
                "label": str(label),
                "study_role": str(role),
                "sweep_path": str(path),
                "sweep_runs_path": str(target.resolve()),
                "manifest_path": str(manifest_path.resolve()),
                "manifest_exists": integrity.exists,
                "manifest_readable": integrity.readable,
                "manifest_sha256": (
                    file_sha256(manifest_path) if manifest_path.is_file() else ""
                ),
                "run_type": integrity.run_type,
                "artifact_count": integrity.artifact_count,
                "artifact_matches": integrity.artifact_match_count,
                "required_artifact_count": integrity.required_artifact_count,
                "required_artifact_matches": integrity.required_artifact_match_count,
                "input_fingerprint_count": integrity.input_fingerprint_count,
                "input_fingerprint_matches": integrity.input_fingerprint_match_count,
                "passed": integrity.passed,
                "error": integrity.error,
                "recommendation": (
                    "use_manifest_backed_sweep"
                    if integrity.passed
                    else "regenerate_sweep_from_current_fingerprinted_market_data"
                ),
            }
        )
    return pd.DataFrame(rows)


def sweep_runs_path(path: str | Path) -> Path:
    resolved = Path(path).resolve()
    return resolved / "sweep_runs.csv" if resolved.is_dir() else resolved


def sweep_manifest_path(path: str | Path) -> Path:
    resolved = Path(path).resolve()
    return (
        resolved / "manifest.json"
        if resolved.is_dir()
        else resolved.parent / "manifest.json"
    )
