"""Configuration parsing and validation."""

from __future__ import annotations

import fnmatch
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from packaging.markers import Marker

from hatch_mojo.types import EMIT_VALUES, EmitType, InstallKind


@dataclass(slots=True, frozen=True)
class JobConfig:
    """Single source configuration entry."""

    name: str
    input: str
    emit: EmitType
    output: str | None
    module: str | None
    install_kind: InstallKind | None
    install_path: str | None
    include_dirs: tuple[str, ...]
    defines: tuple[str, ...]
    flags: tuple[str, ...]
    env: dict[str, str]
    platforms: tuple[str, ...]
    arch: tuple[str, ...]
    marker: str | None
    depends_on: tuple[str, ...]


@dataclass(slots=True, frozen=True)
class HookConfig:
    """Validated plugin config."""

    mojo_bin: str | None
    parallel: bool
    fail_fast: bool
    clean_before_build: bool
    clean_after_build: bool
    skip_editable: bool
    build_dir: str
    include: tuple[str, ...]
    exclude: tuple[str, ...]
    targets: tuple[str, ...]
    jobs: tuple[JobConfig, ...]


def _as_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [str(item) for item in value]
    msg = f"Expected list or string, got {type(value)!r}"
    raise TypeError(msg)


def _bool(value: Any, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    msg = f"Expected bool, got {type(value)!r}"
    raise TypeError(msg)


def _merge_dict(base: dict[str, Any], extra: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    merged.update(extra)
    return merged


def _validate_job(name: str, data: dict[str, Any]) -> JobConfig:
    input_value = data.get("input")
    if not input_value:
        raise ValueError(f"Job '{name}' is missing required 'input'")

    emit_value = data.get("emit", "shared-lib")
    if emit_value not in EMIT_VALUES:
        raise ValueError(f"Job '{name}' has invalid emit '{emit_value}'")

    module = data.get("module")
    if emit_value == "python-extension" and not module:
        raise ValueError(f"Job '{name}' emit=python-extension requires 'module'")

    install_cfg = data.get("install")
    install_kind: InstallKind | None = None
    install_path: str | None = None
    if isinstance(install_cfg, dict):
        install_kind = install_cfg.get("kind")
        install_path = install_cfg.get("path")
        if install_kind and install_kind not in {"package", "data", "scripts", "root", "force-include"}:
            raise ValueError(f"Job '{name}' has invalid install.kind '{install_kind}'")
        if install_kind and not install_path:
            raise ValueError(f"Job '{name}' install requires 'path'")

    if emit_value != "python-extension" and install_kind is None:
        raise ValueError(f"Job '{name}' emit={emit_value} requires explicit install mapping")

    marker_value = data.get("marker")
    if marker_value:
        Marker(str(marker_value))

    return JobConfig(
        name=name,
        input=str(input_value),
        emit=emit_value,
        output=str(data["output"]) if data.get("output") else None,
        module=str(module) if module else None,
        install_kind=install_kind,
        install_path=str(install_path) if install_path else None,
        include_dirs=tuple(_as_list(data.get("include-dirs") or data.get("include_dirs"))),
        defines=tuple(_as_list(data.get("defines"))),
        flags=tuple(_as_list(data.get("flags") or data.get("extra-args") or data.get("extra_args"))),
        env={str(k): str(v) for k, v in dict(data.get("env", {})).items()},
        platforms=tuple(_as_list(data.get("platforms"))),
        arch=tuple(_as_list(data.get("arch"))),
        marker=str(marker_value) if marker_value else None,
        depends_on=tuple(_as_list(data.get("depends-on") or data.get("depends_on"))),
    )


def parse_config(raw: dict[str, Any] | None, *, target_name: str) -> HookConfig:
    """Parse and validate raw Hatch hook config."""
    raw = raw or {}
    profiles = raw.get("profiles", {})
    if not isinstance(profiles, dict):
        raise TypeError("profiles must be a dict")

    jobs_raw = raw.get("jobs") or raw.get("sources") or []
    if not isinstance(jobs_raw, list):
        raise TypeError("jobs/sources must be a list")

    jobs: list[JobConfig] = []
    include = tuple(_as_list(raw.get("include")))
    exclude = tuple(_as_list(raw.get("exclude")))
    for index, job_item in enumerate(jobs_raw):
        if not isinstance(job_item, dict):
            raise TypeError(f"jobs[{index}] must be an object")
        profile_names = _as_list(job_item.get("profiles"))
        merged: dict[str, Any] = {}
        for profile_name in profile_names:
            profile = profiles.get(profile_name)
            if not isinstance(profile, dict):
                raise ValueError(f"Unknown profile '{profile_name}' in jobs[{index}]")
            merged = _merge_dict(merged, profile)
        merged = _merge_dict(merged, job_item)
        name = str(merged.get("name") or f"job-{index + 1}")
        job = _validate_job(name, merged)
        if include and not any(fnmatch.fnmatch(job.input, pattern) for pattern in include):
            continue
        if exclude and any(fnmatch.fnmatch(job.input, pattern) for pattern in exclude):
            continue
        jobs.append(job)

    if target_name not in set(_as_list(raw.get("targets")) or ["wheel"]):
        return HookConfig(
            mojo_bin=None,
            parallel=_bool(raw.get("parallel"), False),
            fail_fast=_bool(raw.get("fail-fast"), True),
            clean_before_build=_bool(raw.get("clean-before-build"), False),
            clean_after_build=_bool(raw.get("clean-after-build"), False),
            skip_editable=_bool(raw.get("skip-editable"), True),
            build_dir=str(raw.get("build-dir") or "build/mojo"),
            include=include,
            exclude=exclude,
            targets=tuple(_as_list(raw.get("targets") or ["wheel"])),
            jobs=(),
        )

    if not jobs:
        raise ValueError("No build jobs resolved from 'jobs'/'sources' configuration")

    build_dir = Path(str(raw.get("build-dir") or "build/mojo"))
    return HookConfig(
        mojo_bin=str(raw.get("mojo-bin")) if raw.get("mojo-bin") else None,
        parallel=_bool(raw.get("parallel"), False),
        fail_fast=_bool(raw.get("fail-fast"), True),
        clean_before_build=_bool(raw.get("clean-before-build"), False),
        clean_after_build=_bool(raw.get("clean-after-build"), False),
        skip_editable=_bool(raw.get("skip-editable"), True),
        build_dir=str(build_dir),
        include=include,
        exclude=exclude,
        targets=tuple(_as_list(raw.get("targets") or ["wheel"])),
        jobs=tuple(jobs),
    )
