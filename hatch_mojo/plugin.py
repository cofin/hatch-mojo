"""Hatch build hook plugin implementation."""

from __future__ import annotations

import contextlib
import shutil
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from hatchling.builders.hooks.plugin.interface import BuildHookInterface

from hatch_mojo.artifacts import register_artifacts
from hatch_mojo.cleaning import EDITABLE_MANIFEST_NAME, clean_from_manifest, save_manifest
from hatch_mojo.compiler import compile_job, discover_mojo
from hatch_mojo.config import parse_config
from hatch_mojo.planner import plan_jobs, plan_jobs_leveled
from hatch_mojo.runtime import bundle_runtime_libs
from hatch_mojo.types import BuildJob

_SOURCE_LAYOUTS = ("", "src", "src/py")


def _copy_editable_artifacts(root: Path, jobs: list[BuildJob]) -> list[Path]:
    """Copy built python-extension artifacts into the source tree for editable installs."""
    copied: list[Path] = []
    for job in jobs:
        if job.emit != "python-extension" or not job.module:
            continue
        parts = job.module.split(".")
        if not parts[1:]:
            continue
        pkg_name = parts[0]
        rel_path = Path(*parts[1:]).with_suffix(job.output_path.suffix)
        for layout in _SOURCE_LAYOUTS:
            pkg_dir = root / layout / pkg_name if layout else root / pkg_name
            if (pkg_dir / "__init__.py").exists() or (pkg_dir / "__init__.mojo").exists():
                dest = pkg_dir / rel_path
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(job.output_path, dest)
                copied.append(dest)
                break
    return copied


def _resolve_dist_name(hook: Any) -> str | None:
    """Extract the distribution name from Hatchling metadata when available."""
    with contextlib.suppress(AttributeError, ValueError):
        core_name = hook.metadata.core.name
        if isinstance(core_name, str) and core_name:
            return core_name
    with contextlib.suppress(AttributeError, ValueError):
        meta_name = hook.metadata.name
        if isinstance(meta_name, str) and meta_name:
            return meta_name
    return None


def _compile_planned_jobs(app: Any, root: Path, config: Any) -> tuple[list[BuildJob], str | None]:
    """Plan and execute build jobs serially or across topological DAG levels."""
    if config.parallel:
        levels = plan_jobs_leveled(root, config)
        planned = [job for level in levels for job in level]
        if not planned:
            return [], None
        mojo_bin = discover_mojo(root, config.mojo_bin)
        for level in levels:
            if len(level) > 1:
                with ThreadPoolExecutor() as pool:
                    futures = [
                        pool.submit(
                            compile_job,
                            mojo_bin=mojo_bin,
                            root=root,
                            job=job,
                            fail_fast=config.fail_fast,
                        )
                        for job in level
                    ]
                    for future in futures:
                        success, log = future.result()
                        if not success:
                            app.display_warning(log)
                        else:
                            app.display_debug(log)
            else:
                for job in level:
                    success, log = compile_job(mojo_bin=mojo_bin, root=root, job=job, fail_fast=config.fail_fast)
                    if not success:
                        app.display_warning(log)
                    else:
                        app.display_debug(log)
        return planned, mojo_bin

    planned = plan_jobs(root, config)
    if not planned:
        return [], None
    mojo_bin = discover_mojo(root, config.mojo_bin)
    for job in planned:
        success, log = compile_job(
            mojo_bin=mojo_bin,
            root=root,
            job=job,
            fail_fast=config.fail_fast,
        )
        if not success:
            app.display_warning(log)
        else:
            app.display_debug(log)
    return planned, mojo_bin


class MojoBuildHook(BuildHookInterface[Any]):
    """Compile Mojo sources and register artifacts for Hatch builds."""

    PLUGIN_NAME = "mojo"

    def initialize(self, version: str, build_data: dict[str, Any]) -> None:
        root = Path(self.root)
        config = parse_config(self.config, target_name=self.target_name)

        if version == "editable" and config.skip_editable:
            return
        if not config.jobs:
            return
        if config.clean_before_build:
            clean_from_manifest(root, config.build_dir, include_editable=(version == "editable"))

        planned, mojo_bin = _compile_planned_jobs(self.app, root, config)
        if not planned:
            return

        manifest_files: list[Path] = [job.output_path for job in planned]
        if config.bundle_libs:
            bundled = bundle_runtime_libs(
                root=root,
                build_dir=config.build_dir,
                jobs=planned,
                mojo_bin=mojo_bin,
                dist_name=_resolve_dist_name(self),
            )
            if bundled.force_include:
                build_data.setdefault("force_include", {}).update(bundled.force_include)
            if bundled.shared_data:
                build_data.setdefault("shared_data", {}).update(bundled.shared_data)
            manifest_files.extend(bundled.staged_files)

        register_artifacts(root=root, build_data=build_data, jobs=planned, target_name=self.target_name)
        if (
            build_data.get("shared_scripts")
            or build_data.get("shared_data")
            or build_data.get("force_include_editable")
        ) and not build_data.get("force_include"):
            target_cfg = getattr(getattr(self, "build_config", None), "target_config", None)
            if isinstance(target_cfg, dict):
                target_cfg.setdefault("bypass-selection", True)
        save_manifest(root, config.build_dir, manifest_files)

        if version == "editable":
            editable_files = _copy_editable_artifacts(root, planned)
            if editable_files:
                save_manifest(root, config.build_dir, editable_files, filename=EDITABLE_MANIFEST_NAME)

    def finalize(self, version: str, build_data: dict[str, Any], artifact_path: str) -> None:
        if version == "editable":
            return
        config = parse_config(self.config, target_name=self.target_name)
        if config.jobs and config.clean_after_build:
            clean_from_manifest(Path(self.root), config.build_dir, include_editable=False)

    def clean(self, versions: list[str]) -> None:
        root = Path(self.root)
        config = parse_config(self.config, target_name=self.target_name)
        clean_from_manifest(root, config.build_dir, include_editable=True)
