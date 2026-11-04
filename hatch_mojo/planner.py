"""Build planning and job expansion."""

from __future__ import annotations

import platform
import sys
from dataclasses import replace
from pathlib import Path

from packaging.markers import Marker

from hatch_mojo.artifacts import resolve_install_target
from hatch_mojo.config import HookConfig, JobConfig, matches_filters
from hatch_mojo.types import BuildJob, EmitType


def _platform_match(job: JobConfig) -> bool:
    if job.platforms and sys.platform not in set(job.platforms):
        return False
    machine = platform.machine().lower()
    if job.arch and machine not in {item.lower() for item in job.arch}:
        return False
    return not (job.marker and not Marker(job.marker).evaluate())


def _get_suffix_map() -> dict[str, str]:
    """Return emit-type to file-suffix mapping for the current platform."""
    if sys.platform == "win32":
        return {
            "python-extension": ".pyd",
            "shared-lib": ".dll",
            "mojoc": ".mojoc",
            "object": ".obj",
            "executable": ".exe",
        }
    if sys.platform == "darwin":
        return {
            "python-extension": ".so",
            "shared-lib": ".dylib",
            "mojoc": ".mojoc",
            "object": ".o",
            "executable": "",
        }
    return {
        "python-extension": ".so",
        "shared-lib": ".so",
        "mojoc": ".mojoc",
        "object": ".o",
        "executable": "",
    }


def _default_output(
    root: Path,
    build_dir: str,
    emit: EmitType,
    module: str | None,
    input_path: Path,
) -> Path:
    """Resolve the default output artifact path under *build_dir*."""
    suffix = _get_suffix_map()[emit]
    if emit == "python-extension" and module:
        parts = module.split(".")
        return root / build_dir / Path(*parts).with_suffix(suffix)
    return root / build_dir / f"{input_path.stem}{suffix}"


def _expand_inputs(root: Path, pattern: str) -> list[Path]:
    if any(token in pattern for token in "*?[]"):
        return sorted(path for path in root.glob(pattern) if path.is_file())
    path = root / pattern
    if not path.exists():
        raise FileNotFoundError(pattern)
    return [path]


def _validate_deps(by_name: dict[str, BuildJob], remaining: dict[str, set[str]]) -> None:
    for name, deps in remaining.items():
        unknown = sorted(dep for dep in deps if dep not in by_name)
        if unknown:
            msg = f"Job '{name}' has unknown dependencies: {', '.join(unknown)}"
            raise ValueError(msg)


def _topological_sort(jobs: list[BuildJob]) -> list[BuildJob]:
    by_name = {job.name: job for job in jobs}
    remaining = {job.name: set(job.depends_on) for job in jobs}
    _validate_deps(by_name, remaining)
    ordered: list[BuildJob] = []
    while remaining:
        ready = sorted(name for name, deps in remaining.items() if not deps)
        if not ready:
            cycle = ", ".join(sorted(remaining))
            raise ValueError(f"Dependency cycle detected among jobs: {cycle}")
        for name in ready:
            ordered.append(by_name[name])
            del remaining[name]
        for deps in remaining.values():
            deps.difference_update(ready)
    return ordered


def _topological_levels(jobs: list[BuildJob]) -> list[list[BuildJob]]:
    """Group jobs into levels where jobs within a level are independent."""
    by_name = {job.name: job for job in jobs}
    remaining = {job.name: set(job.depends_on) for job in jobs}
    _validate_deps(by_name, remaining)
    levels: list[list[BuildJob]] = []
    while remaining:
        ready = sorted(name for name, deps in remaining.items() if not deps)
        if not ready:
            cycle = ", ".join(sorted(remaining))
            raise ValueError(f"Dependency cycle detected among jobs: {cycle}")
        levels.append([by_name[name] for name in ready])
        for name in ready:
            del remaining[name]
        for deps in remaining.values():
            deps.difference_update(ready)
    return levels


def _build_concrete_job(
    root: Path,
    build_dir: str,
    job: JobConfig,
    input_path: Path,
    concrete_name: str,
) -> BuildJob:
    """Instantiate a concrete *BuildJob* with ``{stem}`` template expansion."""
    stem = input_path.stem
    resolved_module = job.module.replace("{stem}", stem) if job.module else None
    resolved_output = job.output.replace("{stem}", stem) if job.output else None
    resolved_install_path = job.install_path.replace("{stem}", stem) if job.install_path else None
    output_path = (
        (root / resolved_output)
        if resolved_output
        else _default_output(root, build_dir, job.emit, resolved_module, input_path)
    )
    return BuildJob(
        name=concrete_name,
        input_path=input_path,
        output_path=output_path,
        emit=job.emit,
        module=resolved_module,
        install_kind=job.install_kind,
        install_path=resolved_install_path,
        include_dirs=job.include_dirs,
        defines=job.defines,
        flags=job.flags,
        env=job.env,
        depends_on=job.depends_on,
    )


def _expand_all_jobs(root: Path, config: HookConfig) -> list[BuildJob]:
    """Expand configured jobs into concrete file-level jobs (unsorted)."""
    jobs: list[BuildJob] = []
    expanded_names: dict[str, tuple[str, ...]] = dict.fromkeys(config.excluded_jobs, ())
    seen_names: set[str] = set()
    seen_outputs: set[Path] = set()
    seen_targets: set[tuple[str, str]] = set()

    for job in config.jobs:
        if not _platform_match(job):
            expanded_names[job.name] = ()
            continue
        try:
            raw_inputs = _expand_inputs(root, job.input)
        except FileNotFoundError:
            raise FileNotFoundError(f"Input '{job.input}' does not exist for job '{job.name}'") from None
        if not raw_inputs:
            raise ValueError(f"No input files resolved for job '{job.name}' pattern '{job.input}'")

        input_paths = [
            path
            for path in raw_inputs
            if matches_filters(path.relative_to(root).as_posix(), config.include, config.exclude)
        ]
        if not input_paths:
            expanded_names[job.name] = ()
            continue

        concrete_names: list[str] = []
        for index, input_path in enumerate(input_paths, start=1):
            concrete_name = job.name if len(input_paths) == 1 else f"{job.name}[{index}]"
            if concrete_name in seen_names:
                raise ValueError(f"Duplicate concrete job name '{concrete_name}'")
            seen_names.add(concrete_name)

            build_job = _build_concrete_job(root, config.build_dir, job, input_path, concrete_name)
            if build_job.output_path in seen_outputs:
                raise ValueError(f"Duplicate output path '{build_job.output_path}' across expanded jobs")
            seen_outputs.add(build_job.output_path)

            if build_job.emit == "python-extension" or build_job.install_kind is not None:
                section = (
                    build_job.install_kind
                    if build_job.emit != "python-extension" and build_job.install_kind in {"scripts", "data"}
                    else "platlib"
                )
                target_key = (section, resolve_install_target(build_job))
                if target_key in seen_targets:
                    raise ValueError(f"Duplicate install target '{target_key[1]}' across expanded jobs")
                seen_targets.add(target_key)

            concrete_names.append(concrete_name)
            jobs.append(build_job)

        expanded_names[job.name] = tuple(concrete_names)

    rewritten: list[BuildJob] = []
    for build_job in jobs:
        deps: list[str] = []
        for dep in build_job.depends_on:
            if dep in expanded_names:
                deps.extend(expanded_names[dep])
            else:
                deps.append(dep)
        rewritten.append(replace(build_job, depends_on=tuple(dict.fromkeys(deps))))
    return rewritten


def plan_jobs(root: Path, config: HookConfig) -> list[BuildJob]:
    """Expand configured jobs into concrete file-level jobs, topologically sorted."""
    return _topological_sort(_expand_all_jobs(root, config))


def plan_jobs_leveled(root: Path, config: HookConfig) -> list[list[BuildJob]]:
    """Expand configured jobs into levels for parallel execution."""
    return _topological_levels(_expand_all_jobs(root, config))
