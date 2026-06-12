from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from collections.abc import Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


MANIFEST_NAME = "manifest.json"


def write_experiment_manifest(
    output_dir: str | Path,
    *,
    run_type: str,
    parameters: Mapping[str, Any] | None = None,
    inputs: Mapping[str, Any] | None = None,
    extra: Mapping[str, Any] | None = None,
    cwd: str | Path | None = None,
) -> Path:
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    manifest = build_experiment_manifest(
        out,
        run_type=run_type,
        parameters=parameters,
        inputs=inputs,
        extra=extra,
        cwd=cwd,
    )
    path = out / MANIFEST_NAME
    path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def build_experiment_manifest(
    output_dir: str | Path,
    *,
    run_type: str,
    parameters: Mapping[str, Any] | None = None,
    inputs: Mapping[str, Any] | None = None,
    extra: Mapping[str, Any] | None = None,
    cwd: str | Path | None = None,
) -> dict[str, Any]:
    out = Path(output_dir)
    repo_cwd = Path(cwd) if cwd is not None else _discover_repo_root(out)
    return {
        "schema_version": 1,
        "generated_at_utc": _utc_now(),
        "run_type": run_type,
        "parameters": _jsonable(parameters or {}),
        "inputs": {name: _input_fingerprint(value) for name, value in (inputs or {}).items()},
        "artifacts": _artifact_fingerprints(out),
        "git": _git_state(repo_cwd),
        "environment": {
            "python": sys.version.split()[0],
            "pandas": pd.__version__,
            "numpy": np.__version__,
        },
        "extra": _jsonable(extra or {}),
    }


def file_sha256(path: str | Path) -> str:
    hasher = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def _input_fingerprint(value: Any) -> Any:
    if isinstance(value, (list, tuple)):
        return [_input_fingerprint(item) for item in value]
    if isinstance(value, Mapping):
        return {str(key): _input_fingerprint(item) for key, item in value.items()}
    if isinstance(value, (str, Path)):
        path = Path(value)
        if path.exists():
            return _path_fingerprint(path)
    return _jsonable(value)


def _path_fingerprint(path: Path) -> dict[str, Any]:
    resolved = path.resolve()
    if resolved.is_file():
        return {
            "path": str(resolved),
            "kind": "file",
            "size_bytes": int(resolved.stat().st_size),
            "sha256": file_sha256(resolved),
        }
    if resolved.is_dir():
        files = [item for item in sorted(resolved.rglob("*")) if item.is_file() and item.name != MANIFEST_NAME]
        tree_hasher = hashlib.sha256()
        for item in files:
            rel = item.relative_to(resolved).as_posix()
            tree_hasher.update(rel.encode("utf-8"))
            tree_hasher.update(file_sha256(item).encode("ascii"))
        return {
            "path": str(resolved),
            "kind": "directory",
            "file_count": int(len(files)),
            "tree_sha256": tree_hasher.hexdigest(),
        }
    return {"path": str(resolved), "kind": "other"}


def _artifact_fingerprints(output_dir: Path) -> list[dict[str, Any]]:
    if not output_dir.exists():
        return []
    rows = []
    for path in sorted(output_dir.rglob("*")):
        if not path.is_file() or path.name == MANIFEST_NAME:
            continue
        rows.append(
            {
                "path": path.relative_to(output_dir).as_posix(),
                "size_bytes": int(path.stat().st_size),
                "sha256": file_sha256(path),
            }
        )
    return rows


def _git_state(cwd: Path) -> dict[str, Any]:
    return {
        "branch": _git(["rev-parse", "--abbrev-ref", "HEAD"], cwd),
        "commit": _git(["rev-parse", "HEAD"], cwd),
        "dirty": bool(_git(["status", "--short"], cwd)),
    }


def _git(args: list[str], cwd: Path) -> str | None:
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=cwd,
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError:
        return None
    if result.returncode != 0:
        return None
    text = result.stdout.strip()
    return text or None


def _discover_repo_root(path: Path) -> Path:
    current = path.resolve()
    if current.is_file():
        current = current.parent
    for candidate in [current, *current.parents]:
        if (candidate / ".git").exists():
            return candidate
    return current


def _jsonable(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_jsonable(item) for item in value]
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, np.generic):
        return value.item()
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    return value


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
