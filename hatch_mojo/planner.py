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


def _default_output(root: Path, job: JobConfig, input_path: Path) -> Path:
    suffix_map = {
        "python-extension": ".so",
        "shared-lib": ".so",
        "static-lib": ".a",
        "object": ".o",
        "executable": "",
    }
    target_suffix = suffix_map[job.emit]
    stem = input_path.stem
    output_name = f"{stem}{target_suffix}"
    return root / ".hatch_mojo" / output_name


def _expand_inputs(root: Path, pattern: str) -> list[Path]:
    if any(token in pattern for token in "*?[]"):
        return sorted(path for path in root.glob(pattern) if path.is_file())
    path = root / pattern
    if not path.exists():
        return []
    return [path]


def _topological_sort(jobs: list[BuildJob]) -> list[BuildJob]:
    by_name = {job.name: job for job in jobs}
    remaining = {job.name: set(job.depends_on) for job in jobs}
    for name, deps in remaining.items():
        unknown = sorted(dep for dep in deps if dep not in by_name)
        if unknown:
            msg = f"Job '{name}' has unknown dependencies: {', '.join(unknown)}"
            raise ValueError(msg)
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


def plan_jobs(root: Path, config: HookConfig) -> list[BuildJob]:
    """Expand configured jobs into concrete file-level jobs."""
    jobs: list[BuildJob] = []
    for job in config.jobs:
        if not _platform_match(job):
            continue
        input_paths = _expand_inputs(root, job.input)
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
    return _topological_sort(jobs)
