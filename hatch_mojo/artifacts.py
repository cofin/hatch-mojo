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


def resolve_install_target(job: BuildJob) -> str:
    """Resolve the archive-relative installation path for *job*."""
    if job.emit == "python-extension":
        if not job.module:
            raise ValueError(f"python-extension job '{job.name}' missing module")
        return _module_dest(job.module, job.output_path)

    if not job.install_kind:
        raise ValueError(f"non-python job '{job.name}' missing install mapping")
    if job.install_kind == "root":
        return job.output_path.name
    if not job.install_path:
        raise ValueError(f"non-python job '{job.name}' missing install mapping")

    if job.install_kind in {"force-include", "scripts"}:
        return (
            f"{job.install_path.strip('/')}/{job.output_path.name}"
            if job.install_path.endswith("/")
            else job.install_path.lstrip("/")
        )
    if job.install_kind == "package":
        return f"{job.install_path.strip('/')}/{job.output_path.name}"
    if job.install_kind == "data":
        cleaned = job.install_path.lstrip("/")
        is_dir = cleaned.endswith("/") or ("/" not in cleaned and "." not in Path(cleaned).name)
        return f"{cleaned.rstrip('/')}/{job.output_path.name}" if is_dir else cleaned
    raise ValueError(f"Unknown install kind '{job.install_kind}' for {job.name}")


def register_artifacts(*, root: Path, build_data: dict[str, Any], jobs: list[BuildJob], target_name: str) -> None:
    """Register built artifacts in Hatch build_data."""
    force_include = build_data.setdefault("force_include", {})

    has_native = False
    for job in jobs:
        target = resolve_install_target(job)
        source = str(job.output_path)
        if job.emit != "python-extension" and job.install_kind == "scripts":
            build_data.setdefault("shared_scripts", {})[source] = target
        elif job.emit != "python-extension" and job.install_kind == "data":
            build_data.setdefault("shared_data", {})[source] = target
        else:
            force_include[source] = target

        if job.emit not in {"object", "mojoc"}:
            has_native = True

    if target_name == "wheel" and has_native:
        build_data["infer_tag"] = True
        build_data["pure_python"] = False
