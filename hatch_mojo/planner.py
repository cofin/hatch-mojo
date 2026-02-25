"""Build planning and job expansion."""

from __future__ import annotations

import platform
import sys
from pathlib import Path

from packaging.markers import Marker, default_environment

from hatch_mojo.config import HookConfig, JobConfig
from hatch_mojo.types import BuildJob


def _platform_match(job: JobConfig) -> bool:
    if job.platforms and sys.platform not in set(job.platforms):
        return False
    machine = platform.machine().lower()
    if job.arch and machine not in {item.lower() for item in job.arch}:
        return False
    marker_env = default_environment()
    return not (job.marker and not Marker(job.marker).evaluate(environment=marker_env))  # type: ignore[arg-type]


def _get_suffix_map() -> dict[str, str]:
    """Return emit-type to file-suffix mapping for the current platform."""
    if sys.platform == "win32":
        return {
            "python-extension": ".pyd",
            "shared-lib": ".dll",
            "static-lib": ".lib",
            "object": ".obj",
            "executable": ".exe",
        }
    if sys.platform == "darwin":
        return {
            "python-extension": ".so",
            "shared-lib": ".dylib",
            "static-lib": ".a",
            "object": ".o",
            "executable": "",
        }
    return {
        "python-extension": ".so",
        "shared-lib": ".so",
        "static-lib": ".a",
        "object": ".o",
        "executable": "",
    }


def _default_output(root: Path, job: JobConfig, input_path: Path) -> Path:
    suffix = _get_suffix_map()[job.emit]
    if job.emit == "python-extension" and job.module:
        # mogemma._core -> .hatch_mojo/mogemma/_core.so
        parts = job.module.split(".")
        return root / ".hatch_mojo" / Path(*parts).with_suffix(suffix)
    return root / ".hatch_mojo" / f"{input_path.stem}{suffix}"


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


def _expand_all_jobs(root: Path, config: HookConfig) -> list[BuildJob]:
    """Expand configured jobs into concrete file-level jobs (unsorted)."""
    jobs: list[BuildJob] = []
    for job in config.jobs:
        if not _platform_match(job):
            continue
        try:
            input_paths = _expand_inputs(root, job.input)
        except FileNotFoundError:
            raise FileNotFoundError(f"Input '{job.input}' does not exist for job '{job.name}'") from None
        if not input_paths:
            raise ValueError(f"No input files resolved for job '{job.name}' pattern '{job.input}'")
        for index, input_path in enumerate(input_paths, start=1):
            output_path = (root / job.output) if job.output else _default_output(root, job, input_path)
            concrete_name = job.name if len(input_paths) == 1 else f"{job.name}[{index}]"
            if any(existing.name == concrete_name for existing in jobs):
                raise ValueError(f"Duplicate concrete job name '{concrete_name}'")
            jobs.append(
                BuildJob(
                    name=concrete_name,
                    input_path=input_path,
                    output_path=output_path,
                    emit=job.emit,
                    module=job.module,
                    install_kind=job.install_kind,
                    install_path=job.install_path,
                    include_dirs=job.include_dirs,
                    defines=job.defines,
                    flags=job.flags,
                    env=job.env,
                    depends_on=job.depends_on,
                )
            )
    return jobs


def plan_jobs(root: Path, config: HookConfig) -> list[BuildJob]:
    """Expand configured jobs into concrete file-level jobs, topologically sorted."""
    return _topological_sort(_expand_all_jobs(root, config))


def plan_jobs_leveled(root: Path, config: HookConfig) -> list[list[BuildJob]]:
    """Expand configured jobs into levels for parallel execution."""
    return _topological_levels(_expand_all_jobs(root, config))
