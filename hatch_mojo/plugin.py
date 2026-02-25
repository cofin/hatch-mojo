"""Hatch build hook plugin implementation."""

from __future__ import annotations

import shutil
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from hatchling.builders.hooks.plugin.interface import BuildHookInterface

from hatch_mojo.artifacts import register_artifacts
from hatch_mojo.cleaning import clean_from_manifest, save_manifest
from hatch_mojo.compiler import compile_job, discover_mojo
from hatch_mojo.config import parse_config
from hatch_mojo.planner import plan_jobs, plan_jobs_leveled
from hatch_mojo.types import BuildJob

_SOURCE_LAYOUTS = ("", "src", "src/py")


def _copy_editable_artifacts(root: Path, jobs: list[BuildJob]) -> None:
    """Copy built python-extension artifacts into the source tree for editable installs."""
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
                break


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
            clean_from_manifest(root, config.build_dir)

        if config.parallel:
            levels = plan_jobs_leveled(root, config)
            planned = [job for level in levels for job in level]
            if not planned:
                return
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
                                self.app.display_warning(log)
                            else:
                                self.app.display_debug(log)
                else:
                    for job in level:
                        success, log = compile_job(mojo_bin=mojo_bin, root=root, job=job, fail_fast=config.fail_fast)
                        if not success:
                            self.app.display_warning(log)
                        else:
                            self.app.display_debug(log)
        else:
            planned = plan_jobs(root, config)
            if not planned:
                return
            mojo_bin = discover_mojo(root, config.mojo_bin)
            for job in planned:
                success, log = compile_job(
                    mojo_bin=mojo_bin,
                    root=root,
                    job=job,
                    fail_fast=config.fail_fast,
                )
                if not success:
                    self.app.display_warning(log)
                else:
                    self.app.display_debug(log)

        register_artifacts(root=root, build_data=build_data, jobs=planned, target_name=self.target_name)
        save_manifest(root, config.build_dir, [job.output_path for job in planned])

        if version == "editable":
            _copy_editable_artifacts(root, planned)

        if config.clean_after_build:
            clean_from_manifest(root, config.build_dir)

    def clean(self, versions: list[str]) -> None:
        root = Path(self.root)
        config = parse_config(self.config, target_name=self.target_name)
        clean_from_manifest(root, config.build_dir)
