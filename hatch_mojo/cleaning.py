"""Cleanup support for generated artifacts."""

from __future__ import annotations

import contextlib
import json
from pathlib import Path

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
    if not build_root.is_dir():
        return
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
    """Unlink tracked files from build manifests and prune empty *build_dir* directories."""
    filenames = (MANIFEST_NAME, EDITABLE_MANIFEST_NAME) if include_editable else (MANIFEST_NAME,)
    manifest_paths = [manifest_path(root, build_dir, filename=name) for name in filenames]
    existing = [path for path in manifest_paths if path.exists()]
    if not existing:
        return

    for path in existing:
        payload = json.loads(path.read_text(encoding="utf-8"))
        for item in payload:
            file_path = Path(item)
            if file_path.exists():
                file_path.unlink()
        path.unlink(missing_ok=True)

    _prune_empty_dirs(root / build_dir)
