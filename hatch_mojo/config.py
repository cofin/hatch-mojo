"""Configuration parsing and validation."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

from packaging.markers import Marker
from packaging.tags import parse_tag
from pathspec import GitIgnoreSpec

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
    bundle_libs: bool
    cache: bool
    build_dir: str
    include: tuple[str, ...]
    exclude: tuple[str, ...]
    targets: tuple[str, ...]
    jobs: tuple[JobConfig, ...]
    wheel_tag: str = "auto"
    excluded_jobs: tuple[str, ...] = ()


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


def _env_bool(env_name: str, raw_val: Any, default: bool) -> bool:
    """Resolve a boolean setting with environment-variable override precedence."""
    env_val = os.getenv(env_name)
    if env_val is not None and env_val.strip() != "":
        lowered = env_val.strip().lower()
        if lowered in {"1", "true", "yes", "on"}:
            return True
        if lowered in {"0", "false", "no", "off"}:
            return False
        raise ValueError(f"Invalid boolean value {env_val!r} for {env_name}")
    return _bool(raw_val, default)


_PEP425_TAG_PARTS = 3


def _validate_wheel_tag(raw_val: Any) -> str:
    """Validate ``wheel-tag`` config or ``HATCH_MOJO_WHEEL_TAG`` override."""
    env_val = os.getenv("HATCH_MOJO_WHEEL_TAG")
    candidate: Any = env_val if (env_val is not None and env_val.strip() != "") else raw_val
    if candidate is None:
        return "auto"
    if not isinstance(candidate, str):
        msg = f"Expected str for wheel-tag, got {type(candidate)!r}"
        raise TypeError(msg)
    val = candidate.strip()
    if val in {"auto", "infer", "py3-none"}:
        return val
    parts = val.split("-")
    if len(parts) != _PEP425_TAG_PARTS or not all(parts):
        msg = f"Invalid wheel-tag {candidate!r}; expected 'auto', 'infer', 'py3-none', or '<py>-<abi>-<plat>'"
        raise ValueError(msg)
    try:
        parsed = parse_tag(val)
    except ValueError as exc:
        msg = f"Invalid wheel-tag {candidate!r}: {exc}"
        raise ValueError(msg) from exc
    if not parsed:
        msg = f"Invalid wheel-tag {candidate!r}"
        raise ValueError(msg)
    return val


_JOB_KEY_ALIASES: dict[str, str] = {
    "include_dirs": "include-dirs",
    "depends_on": "depends-on",
    "extra-args": "flags",
    "extra_args": "flags",
}
_DEDUP_LIST_KEYS: frozenset[str] = frozenset({"include-dirs", "defines", "depends-on"})


def _merge_job_dicts(base: dict[str, Any], extra: dict[str, Any]) -> dict[str, Any]:
    """Deep-merge profile and job dictionaries while preserving flag order."""
    merged = dict(base)
    for raw_key, value in extra.items():
        key = _JOB_KEY_ALIASES.get(raw_key, raw_key)
        if value is None:
            merged.setdefault(key, None)
            continue
        if key == "flags":
            merged["flags"] = [*_as_list(merged.get("flags")), *_as_list(value)]
        elif key in _DEDUP_LIST_KEYS:
            merged[key] = list(dict.fromkeys([*_as_list(merged.get(key)), *_as_list(value)]))
        elif key == "env":
            if not isinstance(value, dict):
                raise TypeError("env must be a dict")
            merged["env"] = {**dict(merged.get("env") or {}), **{str(k): str(v) for k, v in value.items()}}
        else:
            merged[key] = value
    return merged


_REMOVED_MOJO_0X_SUFFIXES: tuple[str, ...] = (".🔥", "📦", ".mojopkg")


def _validate_job(name: str, data: dict[str, Any]) -> JobConfig:
    input_value = data.get("input")
    if not input_value:
        raise ValueError(f"Job '{name}' is missing required 'input'")

    input_str = str(input_value)
    output_raw = data.get("output")
    output_str = str(output_raw) if output_raw else None
    for path_candidate in (input_str, output_str):
        if path_candidate and path_candidate.endswith(_REMOVED_MOJO_0X_SUFFIXES):
            msg = (
                f"Job '{name}' uses removed Mojo 0.x path '{path_candidate}'; "
                "'.🔥', '📦', and '.mojopkg' are unsupported in Mojo 1.x (use '.mojo' or emit='mojoc')"
            )
            raise ValueError(msg)

    emit_value = data.get("emit", "shared-lib")
    if emit_value == "static-lib":
        msg = f"Job '{name}' uses removed emit 'static-lib'; Mojo 1.x does not support static-lib (use 'object' or 'mojoc')"
        raise ValueError(msg)
    if emit_value not in EMIT_VALUES:
        raise ValueError(f"Job '{name}' has invalid emit '{emit_value}'")

    module = data.get("module")
    if emit_value == "python-extension" and not module:
        raise ValueError(f"Job '{name}' emit=python-extension requires 'module'")

    install_cfg = data.get("install")
    if install_cfg is not None and not isinstance(install_cfg, dict):
        raise TypeError(f"Job '{name}' install must be a dict")
    if emit_value == "python-extension" and install_cfg is not None:
        raise ValueError(f"Job '{name}' emit=python-extension does not accept 'install'")

    install_kind: InstallKind | None = None
    install_path: str | None = None
    if isinstance(install_cfg, dict):
        install_kind = install_cfg.get("kind")
        install_path = install_cfg.get("path")
        if install_kind and install_kind not in {"package", "data", "scripts", "root", "force-include"}:
            raise ValueError(f"Job '{name}' has invalid install.kind '{install_kind}'")
        if install_kind and install_kind != "root" and (not install_path or not str(install_path).strip().strip("/")):
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


def matches_filters(rel_posix: str, include: tuple[str, ...], exclude: tuple[str, ...]) -> bool:
    """Return True when *rel_posix* satisfies git-style *include* and *exclude* globs."""
    if include and not GitIgnoreSpec.from_lines(include).match_file(rel_posix):
        return False
    return not (exclude and GitIgnoreSpec.from_lines(exclude).match_file(rel_posix))


def parse_config(raw: dict[str, Any] | None, *, target_name: str) -> HookConfig:
    """Parse and validate raw Hatch hook config."""
    raw = raw or {}
    profiles = raw.get("profiles", {})
    if not isinstance(profiles, dict):
        raise TypeError("profiles must be a dict")

    if "jobs" in raw and raw["jobs"] is not None:
        jobs_raw = raw["jobs"]
    elif "sources" in raw and raw["sources"] is not None:
        jobs_raw = raw["sources"]
    else:
        jobs_raw = []
    if not isinstance(jobs_raw, list):
        raise TypeError("jobs/sources must be a list")

    skip_editable = _env_bool("HATCH_MOJO_SKIP_EDITABLE", raw.get("skip-editable"), False)
    cache = _env_bool("HATCH_MOJO_CACHE", raw.get("cache"), True)
    raw_wheel_tag = raw["wheel-tag"] if "wheel-tag" in raw else raw.get("wheel_tag")
    wheel_tag = _validate_wheel_tag(raw_wheel_tag)

    jobs: list[JobConfig] = []
    excluded_jobs: list[str] = []
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
            merged = _merge_job_dicts(merged, profile)
        merged = _merge_job_dicts(merged, job_item)
        name = str(merged.get("name") or f"job-{index + 1}")
        job = _validate_job(name, merged)
        if not any(ch in job.input for ch in "*?[]"):
            rel_posix = PurePosixPath(job.input.replace("\\", "/")).as_posix()
            if not matches_filters(rel_posix, include, exclude):
                excluded_jobs.append(job.name)
                continue
        jobs.append(job)

    if target_name not in set(_as_list(raw.get("targets")) or ["wheel"]):
        return HookConfig(
            mojo_bin=None,
            parallel=_bool(raw.get("parallel"), False),
            fail_fast=_bool(raw.get("fail-fast"), True),
            clean_before_build=_bool(raw.get("clean-before-build"), False),
            clean_after_build=_bool(raw.get("clean-after-build"), False),
            skip_editable=skip_editable,
            bundle_libs=_bool(raw.get("bundle-libs"), True),
            cache=cache,
            build_dir=str(raw.get("build-dir") or "build/mojo"),
            include=include,
            exclude=exclude,
            targets=tuple(_as_list(raw.get("targets") or ["wheel"])),
            jobs=(),
            wheel_tag=wheel_tag,
            excluded_jobs=(),
        )

    if not jobs_raw:
        raise ValueError("No build jobs resolved from 'jobs'/'sources' configuration")

    build_dir = Path(str(raw.get("build-dir") or "build/mojo"))
    return HookConfig(
        mojo_bin=str(raw.get("mojo-bin")) if raw.get("mojo-bin") else None,
        parallel=_bool(raw.get("parallel"), False),
        fail_fast=_bool(raw.get("fail-fast"), True),
        clean_before_build=_bool(raw.get("clean-before-build"), False),
        clean_after_build=_bool(raw.get("clean-after-build"), False),
        skip_editable=skip_editable,
        bundle_libs=_bool(raw.get("bundle-libs"), True),
        cache=cache,
        build_dir=str(build_dir),
        include=include,
        exclude=exclude,
        targets=tuple(_as_list(raw.get("targets") or ["wheel"])),
        jobs=tuple(jobs),
        wheel_tag=wheel_tag,
        excluded_jobs=tuple(excluded_jobs),
    )
