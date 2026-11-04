"""Cleanup support for generated artifacts."""

from __future__ import annotations

import contextlib
import json
import shutil
from pathlib import Path

from hatch_mojo.compiler import CACHE_FILENAME, RAW_CACHE_DIRNAME

MANIFEST_NAME = "manifest.json"
EDITABLE_MANIFEST_NAME = "editable-manifest.json"


def manifest_path(root: Path, build_dir: str, *, filename: str = MANIFEST_NAME) -> Path:
    """Return the path to a manifest file inside *build_dir*."""
    return root / build_dir / filename


def save_manifest(
    root: Path,
    build_dir: str,
    outputs: list[Path],
    *,
    filename: str = MANIFEST_NAME,
) -> Path:
    """Write deduplicated sorted *outputs* to *filename* inside *build_dir*."""
    path = manifest_path(root, build_dir, filename=filename)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = sorted({str(output) for output in outputs})
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path


def _prune_empty_dirs(build_root: Path) -> None:
    """Remove empty subdirectories inside *build_root* bottom-up, then *build_root* if empty."""
    subdirs = sorted((candidate for candidate in build_root.rglob("*") if candidate.is_dir()), reverse=True)
    for directory in (*subdirs, build_root):
        with contextlib.suppress(OSError):
            directory.rmdir()


def clean_from_manifest(
    root: Path,
    build_dir: str,
    *,
    include_editable: bool = False,
) -> None:
    """Unlink tracked files from build manifests, remove build cache state, and prune empty directories."""
    build_root = root / build_dir
    filenames = (MANIFEST_NAME, EDITABLE_MANIFEST_NAME) if include_editable else (MANIFEST_NAME,)
    manifest_paths = [manifest_path(root, build_dir, filename=name) for name in filenames]
    existing = [path for path in manifest_paths if path.exists()]
    cache_file = build_root / CACHE_FILENAME
    raw_dir = build_root / RAW_CACHE_DIRNAME
    if not existing and not cache_file.exists() and not raw_dir.exists():
        return

    for path in existing:
        payload = json.loads(path.read_text(encoding="utf-8"))
        for item in payload:
            Path(item).unlink(missing_ok=True)
        path.unlink(missing_ok=True)

    cache_file.unlink(missing_ok=True)
    if raw_dir.exists():
        shutil.rmtree(raw_dir, ignore_errors=True)

    _prune_empty_dirs(build_root)
