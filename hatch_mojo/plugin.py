"""Hatch build hook plugin implementation."""

from __future__ import annotations

import contextlib
import shutil
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path, PurePosixPath
from typing import Any

from hatchling.builders.hooks.plugin.interface import BuildHookInterface

from hatch_mojo.artifacts import register_artifacts
from hatch_mojo.cleaning import EDITABLE_MANIFEST_NAME, clean_from_manifest, save_manifest
from hatch_mojo.compiler import compile_job, discover_mojo
from hatch_mojo.config import parse_config
from hatch_mojo.planner import plan_jobs, plan_jobs_leveled
from hatch_mojo.runtime import bundle_runtime_libs, patch_editable_runtime
from hatch_mojo.types import BuildJob

_SOURCE_LAYOUTS = ("", "src", "src/py")


def _resolve_editable_layout(root: Path, build_config: Any) -> tuple[dict[str, Path], list[str]]:
    """Extract local package directories and source roots without evaluating lazy properties."""
    target_cfg = getattr(build_config, "target_config", None)
    global_cfg = getattr(build_config, "build_config", None)

    if isinstance(target_cfg, dict) and "packages" in target_cfg:
        raw_packages = target_cfg["packages"]
    elif isinstance(global_cfg, dict) and "packages" in global_cfg:
        raw_packages = global_cfg["packages"]
    elif target_cfg is None:
        raw_packages = getattr(build_config, "packages", None)
    else:
        raw_packages = None

    if isinstance(target_cfg, dict) and "sources" in target_cfg:
        raw_sources = target_cfg["sources"]
    elif isinstance(global_cfg, dict) and "sources" in global_cfg:
        raw_sources = global_cfg["sources"]
    elif target_cfg is None:
        raw_sources = getattr(build_config, "sources", None)
    else:
        raw_sources = None

    pkg_dirs: dict[str, Path] = {}
    if isinstance(raw_packages, list):
        for entry in raw_packages:
            pkg_path = root / str(entry).strip("/")
            pkg_dirs.setdefault(pkg_path.name, pkg_path)

    source_roots: list[str] = []
    if isinstance(raw_sources, list):
        source_roots.extend(str(item).strip("/") for item in raw_sources)
    elif isinstance(raw_sources, dict):
        source_roots.extend(str(key).strip("/") for key in raw_sources)
    for fallback in _SOURCE_LAYOUTS:
        if fallback not in source_roots:
            source_roots.append(fallback)
    return pkg_dirs, source_roots


def _find_local_package_dir(
    root: Path,
    pkg_name: str,
    pkg_dirs: dict[str, Path],
    source_roots: list[str],
) -> Path | None:
    """Locate the editable source directory for *pkg_name* when present."""
    if pkg_name in pkg_dirs:
        return pkg_dirs[pkg_name]
    for layout in source_roots:
        candidate = root / layout / pkg_name if layout else root / pkg_name
        if (candidate / "__init__.py").exists() or (candidate / "__init__.mojo").exists():
            return candidate
    return None


def _is_dev_mode_exact(build_config: Any) -> bool:
    """Return True when Hatchling editable build uses ``dev-mode-exact``."""
    target_cfg = getattr(build_config, "target_config", None)
    if isinstance(target_cfg, dict) and "dev-mode-exact" in target_cfg:
        return bool(target_cfg["dev-mode-exact"])
    global_cfg = getattr(build_config, "build_config", None)
    if isinstance(global_cfg, dict) and "dev-mode-exact" in global_cfg:
        return bool(global_cfg["dev-mode-exact"])
    return bool(getattr(build_config, "dev_mode_exact", False))


def _stage_editable_jobs(
    root: Path,
    build_dir: str,
    jobs: list[BuildJob],
    build_config: Any,
) -> tuple[list[BuildJob], list[BuildJob]]:
    """Copy compiled outputs to editable destinations, separating in-source vs wheel-staged jobs."""
    pkg_dirs, source_roots = _resolve_editable_layout(root, build_config)
    editable_jobs: list[BuildJob] = []
    uncopied_jobs: list[BuildJob] = []

    for job in jobs:
        dest: Path | None = None
        if job.emit == "python-extension" and job.module and "." in job.module:
            parts = job.module.split(".")
            pkg_dir = _find_local_package_dir(root, parts[0], pkg_dirs, source_roots)
            if pkg_dir is not None:
                dest = pkg_dir / Path(*parts[1:]).with_suffix(job.output_path.suffix)
        elif job.emit != "python-extension" and job.install_kind == "package" and job.install_path:
            rel_parts = PurePosixPath(job.install_path.strip("/")).parts
            pkg_dir = _find_local_package_dir(root, rel_parts[0], pkg_dirs, source_roots) if rel_parts else None
            if pkg_dir is not None:
                sub = Path(*rel_parts[1:]) if len(rel_parts) > 1 else Path()
                dest = pkg_dir / sub / job.output_path.name

        copied_in_source = dest is not None
        if dest is None:
            dest = root / build_dir / "editable" / job.name / job.output_path.name
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(job.output_path, dest)
        staged_job = replace(job, output_path=dest)
        editable_jobs.append(staged_job)
        if not copied_in_source:
            uncopied_jobs.append(staged_job)

    return editable_jobs, uncopied_jobs


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


def _compile_parallel_levels(
    *,
    app: Any,
    root: Path,
    config: Any,
    levels: list[list[BuildJob]],
    mojo_bin: str,
) -> list[BuildJob]:
    """Execute topological build levels in parallel while filtering failed jobs and dependents."""
    succeeded: list[BuildJob] = []
    failed_names: set[str] = set()
    cache_dir = root / config.build_dir

    for level in levels:
        runnable: list[BuildJob] = []
        for job in level:
            blocked = sorted(dep for dep in job.depends_on if dep in failed_names)
            if blocked:
                failed_names.add(job.name)
                app.display_warning(f"Skipping job '{job.name}' due to failed dependencies: {', '.join(blocked)}")
            else:
                runnable.append(job)
        if len(runnable) > 1:
            with ThreadPoolExecutor() as pool:
                pairs = [
                    (
                        job,
                        pool.submit(
                            compile_job,
                            mojo_bin=mojo_bin,
                            root=root,
                            job=job,
                            fail_fast=config.fail_fast,
                            use_cache=config.cache,
                            cache_dir=cache_dir,
                        ),
                    )
                    for job in runnable
                ]
                for job, future in pairs:
                    success, log = future.result()
                    if not success:
                        failed_names.add(job.name)
                        app.display_warning(log)
                    else:
                        succeeded.append(job)
                        app.display_debug(log)
        else:
            for job in runnable:
                success, log = compile_job(
                    mojo_bin=mojo_bin,
                    root=root,
                    job=job,
                    fail_fast=config.fail_fast,
                    use_cache=config.cache,
                    cache_dir=cache_dir,
                )
                if not success:
                    failed_names.add(job.name)
                    app.display_warning(log)
                else:
                    succeeded.append(job)
                    app.display_debug(log)
    return succeeded


def _compile_planned_jobs(app: Any, root: Path, config: Any) -> tuple[list[BuildJob], str | None]:
    """Plan and execute build jobs serially or across topological DAG levels, filtering failures."""
    if config.parallel:
        levels = plan_jobs_leveled(root, config)
        if not any(levels):
            return [], None
        mojo_bin = discover_mojo(root, config.mojo_bin)
        return _compile_parallel_levels(app=app, root=root, config=config, levels=levels, mojo_bin=mojo_bin), mojo_bin

    planned = plan_jobs(root, config)
    if not planned:
        return [], None
    mojo_bin = discover_mojo(root, config.mojo_bin)
    cache_dir = root / config.build_dir
    succeeded: list[BuildJob] = []
    failed_names: set[str] = set()
    for job in planned:
        blocked = sorted(dep for dep in job.depends_on if dep in failed_names)
        if blocked:
            failed_names.add(job.name)
            app.display_warning(f"Skipping job '{job.name}' due to failed dependencies: {', '.join(blocked)}")
            continue
        success, log = compile_job(
            mojo_bin=mojo_bin,
            root=root,
            job=job,
            fail_fast=config.fail_fast,
            use_cache=config.cache,
            cache_dir=cache_dir,
        )
        if not success:
            failed_names.add(job.name)
            app.display_warning(log)
        else:
            succeeded.append(job)
            app.display_debug(log)
    return succeeded, mojo_bin


def _apply_zero_python_bypass(build_config: Any, build_data: dict[str, Any]) -> None:
    """Enable ``bypass-selection`` automatically when wheel artifacts live solely outside ``force_include``."""
    if (
        build_data.get("shared_scripts") or build_data.get("shared_data") or build_data.get("force_include_editable")
    ) and not build_data.get("force_include"):
        target_cfg = getattr(build_config, "target_config", None)
        if isinstance(target_cfg, dict):
            target_cfg.setdefault("bypass-selection", True)


def _initialize_editable(
    *,
    hook: Any,
    root: Path,
    config: Any,
    planned: list[BuildJob],
    mojo_bin: str | None,
    build_data: dict[str, Any],
) -> None:
    """Stage, RPATH-patch, and register editable build artifacts."""
    build_cfg = getattr(hook, "build_config", None)
    editable_jobs, uncopied_jobs = _stage_editable_jobs(root, config.build_dir, planned, build_cfg)
    editable_files = [ej.output_path for ej in editable_jobs]

    if config.bundle_libs:
        editable_files.extend(patch_editable_runtime(root, config.build_dir, editable_jobs, mojo_bin))

    if uncopied_jobs:
        temp_bd: dict[str, Any] = {}
        register_artifacts(root=root, build_data=temp_bd, jobs=uncopied_jobs, target_name=hook.target_name)
        if temp_bd.get("shared_scripts"):
            build_data.setdefault("shared_scripts", {}).update(temp_bd["shared_scripts"])
        if temp_bd.get("shared_data"):
            build_data.setdefault("shared_data", {}).update(temp_bd["shared_data"])
        if temp_bd.get("force_include"):
            if _is_dev_mode_exact(build_cfg):
                fi_edit = build_data.setdefault("force_include_editable", {})
                get_fi = getattr(build_cfg, "get_force_include", None)
                if callable(get_fi):
                    existing_fi = get_fi()
                    if isinstance(existing_fi, dict):
                        for key, val in existing_fi.items():
                            fi_edit.setdefault(key, val)
                fi_edit.update(temp_bd["force_include"])
            else:
                build_data.setdefault("force_include", {}).update(temp_bd["force_include"])

    _apply_zero_python_bypass(build_cfg, build_data)
    save_manifest(root, config.build_dir, [job.output_path for job in planned])
    if editable_files:
        save_manifest(root, config.build_dir, editable_files, filename=EDITABLE_MANIFEST_NAME)


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

        if version == "editable":
            _initialize_editable(
                hook=self,
                root=root,
                config=config,
                planned=planned,
                mojo_bin=mojo_bin,
                build_data=build_data,
            )
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

        build_cfg = getattr(self, "build_config", None)
        register_artifacts(
            root=root,
            build_data=build_data,
            jobs=planned,
            target_name=self.target_name,
            wheel_tag=config.wheel_tag,
            macos_max_compat=bool(getattr(build_cfg, "macos_max_compat", False)),
        )
        _apply_zero_python_bypass(build_cfg, build_data)
        save_manifest(root, config.build_dir, manifest_files)

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
