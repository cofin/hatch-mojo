"""Artifact mapping for Hatch build data."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from hatch_mojo.types import BuildJob


def _module_dest(module: str, output: Path) -> str:
    module_path = module.replace(".", "/")
    if "/" in module_path:
        package, _, leaf = module_path.rpartition("/")
        return f"{package}/{leaf}{output.suffix}"
    return f"{module_path}{output.suffix}"


def register_artifacts(*, root: Path, build_data: dict[str, Any], jobs: list[BuildJob], target_name: str) -> None:
    """Register built artifacts in Hatch build_data."""
    force_include = build_data.setdefault("force_include", {})
    artifacts = build_data.setdefault("artifacts", [])

    has_native = False
    for job in jobs:
        source = str(job.output_path)
        if job.emit == "python-extension":
            if not job.module:
                raise ValueError(f"python-extension job '{job.name}' missing module")
            destination = _module_dest(job.module, job.output_path)
            force_include[source] = destination
            has_native = True
            continue

        if not job.install_kind or not job.install_path:
            raise ValueError(f"non-python job '{job.name}' missing install mapping")

        if job.install_kind == "force-include":
            force_include[source] = job.install_path
        elif job.install_kind == "package":
            force_include[source] = f"{job.install_path.rstrip('/')}/{job.output_path.name}"
        elif job.install_kind == "root":
            force_include[source] = job.output_path.name
        elif job.install_kind in {"data", "scripts"}:
            artifacts.append(job.output_path.relative_to(root).as_posix())
            force_include[source] = f"{job.install_path.rstrip('/')}/{job.output_path.name}"
        else:
            raise ValueError(f"Unknown install kind '{job.install_kind}' for {job.name}")

        if job.emit != "object":
            has_native = True

    if target_name == "wheel" and has_native:
        build_data["infer_tag"] = True
        build_data["pure_python"] = False
