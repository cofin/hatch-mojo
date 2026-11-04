"""Shared types and constants."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

EmitType = Literal["python-extension", "shared-lib", "mojoc", "object", "executable"]
InstallKind = Literal["package", "data", "scripts", "root", "force-include"]

EMIT_VALUES: tuple[EmitType, ...] = ("python-extension", "shared-lib", "mojoc", "object", "executable")


@dataclass(slots=True, frozen=True)
class BuildJob:
    """A concrete, expanded build job."""

    name: str
    input_path: Path
    output_path: Path
    emit: EmitType
    module: str | None
    install_kind: InstallKind | None
    install_path: str | None
    include_dirs: tuple[str, ...]
    defines: tuple[str, ...]
    flags: tuple[str, ...]
    env: dict[str, str]
    depends_on: tuple[str, ...]


@dataclass(slots=True, frozen=True)
class RuntimeBundleResult:
    """Staged runtime library mappings for Hatch wheel inclusion."""

    force_include: dict[str, str]
    shared_data: dict[str, str]
    staged_files: tuple[Path, ...]
