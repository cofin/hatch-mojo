"""Artifact mapping for Hatch build data."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from hatchling.builders.macos import process_macos_plat_tag
from packaging.tags import sys_tags

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


def resolve_host_platform_tag(*, macos_max_compat: bool = False) -> str:
    """Resolve the Hatchling-compatible PEP 425 host platform tag."""
    plat = next(
        (tag.platform for tag in sys_tags() if "manylinux" not in tag.platform and "musllinux" not in tag.platform),
        "any",
    )
    if sys.platform == "darwin":
        return process_macos_plat_tag(plat, compat=macos_max_compat)
    return plat


def register_artifacts(
    *,
    root: Path,
    build_data: dict[str, Any],
    jobs: list[BuildJob],
    target_name: str,
    wheel_tag: str = "auto",
    macos_max_compat: bool = False,
) -> None:
    """Register built artifacts and wheel tag policy in Hatch ``build_data``."""
    force_include = build_data.setdefault("force_include", {})

    has_native = False
    has_extension = False
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
        if job.emit == "python-extension":
            has_extension = True

    if target_name != "wheel":
        return

    if wheel_tag not in {"auto", "infer", "py3-none"}:
        if has_native:
            build_data["pure_python"] = False
        build_data["infer_tag"] = False
        build_data["tag"] = wheel_tag
        return

    if not has_native:
        return

    build_data["pure_python"] = False
    effective_policy = ("infer" if has_extension else "py3-none") if wheel_tag == "auto" else wheel_tag
    if effective_policy == "infer":
        build_data["infer_tag"] = True
    else:
        build_data["infer_tag"] = False
        build_data["tag"] = f"py3-none-{resolve_host_platform_tag(macos_max_compat=macos_max_compat)}"
