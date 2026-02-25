"""Cleanup support for generated artifacts."""

from __future__ import annotations

import json
from pathlib import Path

MANIFEST_NAME = "manifest.json"


def manifest_path(root: Path, build_dir: str) -> Path:
    return root / build_dir / MANIFEST_NAME


def save_manifest(root: Path, build_dir: str, outputs: list[Path]) -> None:
    path = manifest_path(root, build_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = [str(output) for output in outputs]
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def clean_from_manifest(root: Path, build_dir: str) -> None:
    path = manifest_path(root, build_dir)
    if not path.exists():
        return
    payload = json.loads(path.read_text(encoding="utf-8"))
    for item in payload:
        file_path = Path(item)
        if file_path.exists():
            file_path.unlink()
    path.unlink(missing_ok=True)
