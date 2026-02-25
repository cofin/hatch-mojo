"""Hatch build hook plugin implementation."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from hatchling.builders.hooks.plugin.interface import BuildHookInterface

from hatch_mojo.artifacts import register_artifacts
from hatch_mojo.cleaning import clean_from_manifest, save_manifest
from hatch_mojo.compiler import compile_job, discover_mojo
from hatch_mojo.config import parse_config
from hatch_mojo.planner import plan_jobs


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

        planned = plan_jobs(root, config)
        if not planned:
            return

        mojo_bin = discover_mojo(root, config.mojo_bin)
        if config.parallel and len(planned) > 1 and all(not job.depends_on for job in planned):
            with ThreadPoolExecutor() as pool:
                futures = [
                    pool.submit(
                        compile_job,
                        mojo_bin=mojo_bin,
                        root=root,
                        job=job,
                        fail_fast=config.fail_fast,
                    )
                    for job in planned
                ]
                for future in futures:
                    success, log = future.result()
                    if not success:
                        self.app.display_warning(log)
                    else:
                        self.app.display_debug(log)
        else:
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

        if config.clean_after_build:
            clean_from_manifest(root, config.build_dir)

    def clean(self, versions: list[str]) -> None:
        root = Path(self.root)
        config = parse_config(self.config, target_name=self.target_name)
        clean_from_manifest(root, config.build_dir)
