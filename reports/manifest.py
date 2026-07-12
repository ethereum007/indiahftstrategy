from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


MANIFEST_NAME = "manifest.json"
FILE_HASH_CHUNK_SIZE = 64 * 1024


@dataclass(frozen=True)
class ManifestIntegrity:
    manifest_path: Path
    root: Path
    exists: bool = False
    readable: bool = False
    run_type: str = ""
    expected_run_type: str = ""
    run_type_matches: bool = False
    artifact_count: int = 0
    artifact_match_count: int = 0
    required_artifact_count: int = 0
    required_artifact_match_count: int = 0
    input_fingerprint_count: int = 0
    input_fingerprint_match_count: int = 0
    passed: bool = False
    error: str = ""


def write_experiment_manifest(
    output_dir: str | Path,
    *,
    run_type: str,
    parameters: Mapping[str, Any] | None = None,
    inputs: Mapping[str, Any] | None = None,
    extra: Mapping[str, Any] | None = None,
    artifact_exclude_paths: tuple[str | Path, ...] = (),
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
        artifact_exclude_paths=artifact_exclude_paths,
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
    artifact_exclude_paths: tuple[str | Path, ...] = (),
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
        "artifacts": _artifact_fingerprints(
            out,
            exclude_paths=artifact_exclude_paths,
        ),
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
        for chunk in iter(lambda: handle.read(FILE_HASH_CHUNK_SIZE), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def verify_experiment_manifest(
    manifest_path: str | Path,
    *,
    expected_run_type: str | None = None,
    required_artifacts: list[str] | tuple[str, ...] = (),
    require_input_fingerprints: bool = False,
) -> ManifestIntegrity:
    path = Path(manifest_path).resolve()
    root = path.parent
    expected = str(expected_run_type or "").strip()
    required = [_manifest_artifact_name(item) for item in required_artifacts]
    if not path.is_file():
        return ManifestIntegrity(
            manifest_path=path,
            root=root,
            expected_run_type=expected,
            required_artifact_count=len(required),
            error="manifest_missing",
        )
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError):
        return ManifestIntegrity(
            manifest_path=path,
            root=root,
            exists=True,
            expected_run_type=expected,
            required_artifact_count=len(required),
            error="manifest_unreadable",
        )
    if not isinstance(payload, dict):
        return ManifestIntegrity(
            manifest_path=path,
            root=root,
            exists=True,
            readable=True,
            expected_run_type=expected,
            required_artifact_count=len(required),
            error="manifest_not_object",
        )

    run_type = str(payload.get("run_type", "")).strip()
    run_type_matches = bool(run_type and (not expected or run_type == expected))
    artifacts_value = payload.get("artifacts", [])
    artifacts = artifacts_value if isinstance(artifacts_value, list) else []
    artifact_matches: dict[str, bool] = {}
    for item in artifacts:
        name = _manifest_artifact_name(item.get("path", "")) if isinstance(item, dict) else ""
        artifact_matches[name] = _manifest_artifact_current(item, root)
    artifact_match_count = sum(artifact_matches.values())
    required_match_count = sum(bool(artifact_matches.get(name, False)) for name in required)

    fingerprints = list(_manifest_input_fingerprints(payload.get("inputs", {})))
    input_match_count = sum(_manifest_fingerprint_current(item) for item in fingerprints)
    artifacts_passed = bool(artifacts) and artifact_match_count == len(artifacts)
    required_passed = required_match_count == len(required)
    inputs_passed = input_match_count == len(fingerprints) and (
        bool(fingerprints) or not require_input_fingerprints
    )
    passed = bool(run_type_matches and artifacts_passed and required_passed and inputs_passed)
    error = ""
    if not run_type:
        error = "run_type_missing"
    elif not run_type_matches:
        error = "run_type_mismatch"
    elif not artifacts:
        error = "artifacts_missing"
    elif artifact_match_count != len(artifacts):
        error = "artifact_drift"
    elif not required_passed:
        error = "required_artifact_missing_or_drifted"
    elif input_match_count != len(fingerprints):
        error = "input_drift"
    elif require_input_fingerprints and not fingerprints:
        error = "input_fingerprints_missing"
    return ManifestIntegrity(
        manifest_path=path,
        root=root,
        exists=True,
        readable=True,
        run_type=run_type,
        expected_run_type=expected,
        run_type_matches=run_type_matches,
        artifact_count=len(artifacts),
        artifact_match_count=artifact_match_count,
        required_artifact_count=len(required),
        required_artifact_match_count=required_match_count,
        input_fingerprint_count=len(fingerprints),
        input_fingerprint_match_count=input_match_count,
        passed=passed,
        error=error,
    )


def manifest_dependency_paths(manifest_path: str | Path) -> list[Path]:
    """Return all recursively manifested input paths below a manifest."""

    found: dict[str, Path] = {}
    seen_manifests: set[Path] = set()

    def visit(raw_path: str | Path) -> None:
        path = Path(raw_path).resolve()
        if path in seen_manifests or not path.is_file():
            return
        seen_manifests.add(path)
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError, json.JSONDecodeError):
            return
        if not isinstance(payload, Mapping):
            return
        for fingerprint in _manifest_input_fingerprints(
            payload.get("inputs", {})
        ):
            dependency = Path(str(fingerprint["path"])).resolve()
            found[str(dependency)] = dependency
            nested_manifest = (
                dependency
                if dependency.is_file() and dependency.name == MANIFEST_NAME
                else dependency / MANIFEST_NAME
            )
            if nested_manifest.is_file():
                resolved_nested = nested_manifest.resolve()
                found[str(resolved_nested)] = resolved_nested
                visit(resolved_nested)

    root_manifest = Path(manifest_path).resolve()
    visit(root_manifest)
    found.pop(str(root_manifest), None)
    return [found[key] for key in sorted(found)]


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


def _manifest_artifact_current(value: Any, root: Path) -> bool:
    if not isinstance(value, Mapping):
        return False
    raw_path = str(value.get("path", "")).strip()
    if not raw_path:
        return False
    relative = Path(raw_path)
    if relative.is_absolute():
        return False
    resolved_root = root.resolve()
    candidate = (resolved_root / relative).resolve()
    try:
        candidate.relative_to(resolved_root)
    except ValueError:
        return False
    try:
        return bool(
            candidate.is_file()
            and int(value.get("size_bytes", -1)) == int(candidate.stat().st_size)
            and str(value.get("sha256", "")) == file_sha256(candidate)
        )
    except (OSError, TypeError, ValueError):
        return False


def _manifest_artifact_name(value: Any) -> str:
    name = str(value).replace("\\", "/")
    while name.startswith("./"):
        name = name[2:]
    return name


def _manifest_input_fingerprints(value: Any) -> Iterator[dict[str, Any]]:
    if isinstance(value, Mapping):
        fingerprint = dict(value)
        if fingerprint.get("kind") in {"file", "directory"} and fingerprint.get("path"):
            yield fingerprint
            return
        for item in fingerprint.values():
            yield from _manifest_input_fingerprints(item)
    elif isinstance(value, list):
        for item in value:
            yield from _manifest_input_fingerprints(item)


def _manifest_fingerprint_current(fingerprint: dict[str, Any]) -> bool:
    path = Path(str(fingerprint.get("path", "")))
    try:
        if fingerprint.get("kind") == "file":
            return bool(
                path.is_file()
                and int(fingerprint.get("size_bytes", -1)) == int(path.stat().st_size)
                and str(fingerprint.get("sha256", "")) == file_sha256(path)
            )
        if fingerprint.get("kind") != "directory" or not path.is_dir():
            return False
        files = [
            item
            for item in sorted(path.rglob("*"))
            if item.is_file() and item.name != MANIFEST_NAME
        ]
        hasher = hashlib.sha256()
        for item in files:
            hasher.update(item.relative_to(path).as_posix().encode("utf-8"))
            hasher.update(file_sha256(item).encode("ascii"))
        return bool(
            int(fingerprint.get("file_count", -1)) == len(files)
            and str(fingerprint.get("tree_sha256", "")) == hasher.hexdigest()
        )
    except (OSError, TypeError, ValueError):
        return False


def _artifact_fingerprints(
    output_dir: Path,
    *,
    exclude_paths: tuple[str | Path, ...] = (),
) -> list[dict[str, Any]]:
    if not output_dir.exists():
        return []
    resolved_output = output_dir.resolve()
    excluded: list[Path] = []
    for value in exclude_paths:
        raw_path = Path(value)
        candidate = (
            raw_path.resolve()
            if raw_path.is_absolute()
            else (resolved_output / raw_path).resolve()
        )
        try:
            candidate.relative_to(resolved_output)
        except ValueError as exc:
            raise ValueError(
                "artifact exclusion escapes the output directory"
            ) from exc
        excluded.append(candidate)
    rows = []
    for path in sorted(output_dir.rglob("*")):
        if not path.is_file() or path.name == MANIFEST_NAME:
            continue
        resolved_path = path.resolve()
        if any(
            resolved_path == excluded_path
            or excluded_path in resolved_path.parents
            for excluded_path in excluded
        ):
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
    return (
        datetime.now(timezone.utc)
        .isoformat(timespec="microseconds")
        .replace("+00:00", "Z")
    )
