---
type: Spec
flow_id: editable-planner-and-caching
title: "Editable Installs, Glob/DAG Planner Fixes & Digest Build Cache"
description: "Deliver working editable installs with SDK-direct RPATHs, deep profile merging, collision-free multi-file globs, fail-fast filtering, and SHA-256 build caching."
state: completed
parent_prd: v0-2-overhaul
research:
  - ../v0-2-overhaul/research/mojo-packaging-landscape-audit_20261104.md
plan_revision: 3
plan_commit: ad4930f
state_revision: 5
current_task: null
last_verified_checkpoint: 5731ab7
created_at: 2026-11-04T05:05:00Z
updated_at: 2026-11-04T20:03:00Z
tags: [feature, editable, planner, config, caching]
---

# Flow: Editable Installs, Glob/DAG Planner Fixes & Digest Build Cache

## 1. Specification & Context

### 1.1 Problem Statement & Objectives
Even after CLI and Hatchling `finalize` alignment, developer ergonomics and multi-job planning in `hatch-mojo` suffer from four defects:
1. **Editable builds fail at import time**: `skip-editable` defaults to `true`, and when set to `false`, extensions receive relative `../<pkg>.libs` RPATHs without `<pkg>.libs` beside the source package while `build_data["force_include"]` duplicates stale `.so` files into `site-packages/` and hardcoded `_SOURCE_LAYOUTS` ignores `self.build_config.packages`/`sources` and `dev_mode_exact`.
2. **Shallow profile merging & loose config validation**: `config.py::_merge_dict` overwrites profile `flags`, `include-dirs`, `defines`, `depends-on`, and `env` instead of concatenating/merging them; `{"jobs": {}}` raises `ValueError` instead of `TypeError`; and `install` on `python-extension` jobs is silently ignored.
3. **Glob output collisions, broken `depends-on`, & `fail-fast = false` crashes**: `config.py` applies `fnmatch` to unexpanded glob strings; multi-file globs overwrite a single `output_path` and break downstream `depends-on` references to the base job name; and `fail-fast = false` leaves failed jobs in `planned`, crashing downstream bundling/archiving.
4. **No incremental build cache**: Every `uv sync` or `hatch build` invokes `mojo build` unconditionally (~3.6 GB RAM and multi-second latency per job) even when sources, `-I` headers, flags, and compiler binary are unchanged.

**Objectives**: Make `uv sync` / `pip install -e .` work out-of-the-box (`skip-editable = false` default + `HATCH_MOJO_SKIP_EDITABLE` override) with persistent SDK-direct RPATHs (and `<build_dir>/editable.libs` fallback for ephemeral PEP 517 SDKs), fix profile merging and multi-glob DAG expansion, isolate `fail-fast = false` failures cleanly, and skip unchanged jobs via SHA-256 content-digest caching (`cache = true` default).

**Non-Goals**: `wheel-tag` (`py3-none`) configuration, PEP 639 repository metadata, CI matrix expansion, and README rewrite (owned by Chapter 4).

### 1.2 Upstream Execution Baseline
- **Branch**: `main`
- **Parent PRD**: [`v0-2-overhaul`](../v0-2-overhaul/spec.md) (Chapter 3 of 4)
- **Prerequisite Child Flow**: [`hatchling-lifecycle-and-bundling`](../hatchling-lifecycle-and-bundling/spec.md)

### 1.3 Code Analysis & Seam Summary

| Area | Files Examined (`path/to/file::Symbol`) | Public Seam, Dependency Category & Integration |
| --- | --- | --- |
| Config & Profiles | `hatch_mojo/config.py::HookConfig`, `parse_config`, `_validate_job` | In-process TOML parser adding `cache`, `skip_editable=False` default, env overrides, and deep profile merging. |
| Glob & DAG Planner | `hatch_mojo/planner.py::_expand_all_jobs`, `plan_jobs`, `plan_jobs_leveled` | Local-substitutable planner with `pathspec` filtering, `{stem}` templating, and `depends_on` rewrite. |
| Editable Runtime | `hatch_mojo/runtime.py::patch_editable_runtime`, `hatch_mojo/plugin.py::MojoBuildHook.initialize` | External/Host seam patching editable RPATHs to `modular_lib` (or `<build_dir>/editable.libs`) and honoring `build_config.packages` / `dev_mode_exact`. |
| Digest Build Cache | `hatch_mojo/compiler.py::compute_job_digest`, `compile_job`, `hatch_mojo/cleaning.py::clean_from_manifest` | Local-substitutable SHA-256 `cache.json` persistence skipping redundant `mojo` invocations. |

### 1.4 Relevant Patterns, Domain Terms & Knowledge Chapters
- Architecture & Domain: [`build-pipeline-seams.md`](../../knowledge/architecture/build-pipeline-seams.md), [`mojo-wheel-packaging.md`](../../knowledge/domains/mojo-wheel-packaging.md)
- Patterns & Gotchas: [`typed-slotted-models.md`](../../knowledge/patterns/typed-slotted-models.md), [`platform-linking-and-build-quirks.md`](../../knowledge/gotchas/platform-linking-and-build-quirks.md)
- Project Skills: [`hatch-build-pipeline`](../../../skills/hatch-build-pipeline/SKILL.md), [`native-runtime-bundling`](../../../skills/native-runtime-bundling/SKILL.md)

## 2. Requirements & Architecture

### 2.1 Functional Requirements
- **R1 (Deep Profile Merging, Strict Config & Env Overrides)**: In `parse_config`, reject non-list `jobs`/`sources` (including `{}`) with `TypeError`; reject non-dict `install` with `TypeError`, empty `str(install.path).strip().strip("/")` (when `install.kind != "root"`) with `ValueError`, and `install` on `python-extension` with `ValueError`; concatenate profile + job `flags` verbatim while deduplicating `include-dirs`, `defines`, and `depends-on` in order and merging `env` dicts; default `skip_editable = False` (overridable via `HATCH_MOJO_SKIP_EDITABLE`) and add `cache: bool = True` (overridable via `HATCH_MOJO_CACHE`).
- **R2 (`pathspec` Filtering, `{stem}` Multi-Globs & `depends-on` Expansion)**: Record literal job names skipped by `include`/`exclude` in `HookConfig.excluded_jobs: tuple[str, ...] = ()` (raising `"No build jobs resolved"` only when raw `jobs`/`sources` itself is empty) and evaluate `pathspec.GitIgnoreSpec` after `_expand_inputs` so excluded literal or globbed jobs map to `()` in `depends_on` rewriting without false `"unknown dependencies"` errors; support `{stem}` substitution in `job.module`, `job.output`, and `job.install_path`; reject multi-file globs that produce duplicate `output_path` or duplicate `(install_kind, resolve_install_target(build_job))` entries; and remove `# type: ignore` in `_platform_match` via `Marker(job.marker).evaluate()`.
- **R3 (Package-Aware Editable Installs & `fail-fast = false` Safety)**: When `fail-fast = false`, omit failed jobs (and dependents of failed jobs) from downstream runtime bundling and artifact registration. When `version == "editable"`: read raw `"packages"`/`"sources"` from `build_config.target_config`/`build_config` dicts before fallback `("", "src", "src/py")` (avoiding premature `WheelBuilderConfig.default_packages()` evaluation); copy dotted package extensions (`"." in job.module`) and `install.kind == "package"` artifacts into resolved local package directories in **both** `dev_mode_exact` modes while staging non-package/top-level/`scripts`/`data` editable binaries into `<build_dir>/editable/`; run `patch_editable_runtime` on those editable destination binaries (leaving `<build_dir>` compiler outputs unmutated, setting RPATH directly to persistent `modular_lib` or staging relocated/signed `<build_dir>/editable.libs` when `_is_ephemeral_sdk` matches `tempfile.gettempdir()`, `builds-v0`, `.tmp*`, or `pip-build-env-*`); route uncopied top-level/`root`/`force-include` `platlib` artifacts via `build_data["force_include_editable"]` (seeded from `build_config.get_force_include()`) when `dev_mode_exact` is `True` or `build_data["force_include"]` when `False`; and save editable outputs in `editable-manifest.json`.
- **R4 (SHA-256 Digest & Pristine Raw Output Cache)**: Compute `compute_job_digest(mojo_bin=..., root=..., job=..., cache_dir=...)` over `shutil.which`-resolved compiler stat fingerprint (`resolved_path`, `st_mtime_ns`, `st_size`), `emit`, `module`, `flags`, `defines`, `include_dirs`, sorted `env`, `job.input_path` SHA-256, recursive `rglob` `*.mojo` + `*.mojoc` SHA-256s in `job.input_path.parent` (excluding `cache_dir` unless in `include_dirs`) and `job.include_dirs`, plus existing file paths in `job.flags` and upstream `job.depends_on` outputs. Store pristine unpatched compiler outputs in `<build_dir>/.raw/<digest><suffix>` alongside `<build_dir>/cache.json` under a `threading.Lock`, restoring the clean raw output onto `job.output_path` on every cache hit so RPATH mutations never poison subsequent builds, and remove `.raw/` + `cache.json` inside `clean_from_manifest`.

### 2.2 Public Interfaces, Deep Modules & Seam Contracts
- `hatch_mojo/config.py::HookConfig`: Adds `cache: bool` (default `True`) and `excluded_jobs: tuple[str, ...] = ()`; `skip_editable` defaults to `False`.
- `hatch_mojo/runtime.py::patch_editable_runtime(root: Path, build_dir: str, jobs: list[BuildJob], mojo_bin: str | None) -> tuple[Path, ...]`: Encapsulates persistent-SDK vs. ephemeral-tempdir RPATH patching on Linux (`patchelf`) and macOS (`install_name_tool` + `codesign`), operating on editable destination copies (`dataclasses.replace(job, output_path=dest)`).
- `hatch_mojo/compiler.py::compute_job_digest(*, mojo_bin: str, root: Path, job: BuildJob, cache_dir: Path | None = None) -> str` and `compile_job(*, mojo_bin: str, root: Path, job: BuildJob, fail_fast: bool = True, use_cache: bool = False, cache_dir: Path | None = None) -> tuple[bool, str]`.

### 2.3 Non-Functional & Safety Constraints
- Preserve repeated flag tokens (e.g. `["-Xlinker", "-a", "-Xlinker", "-b"]`) in `flags` during profile merging; never `set()`-deduplicate positional CLI flag sequences.
- Guard `cache.json` reads/writes with `threading.Lock` so `parallel = true` `ThreadPoolExecutor` builds never corrupt JSON state.

### 2.4 Acceptance Scenarios (Given / When / Then)
- **Scenario 1 (Profile flag concatenation)**: Given profile `base` with `flags = ["-Xlinker", "-foo"]` and job with `flags = ["-Xlinker", "-bar"]`, when `parse_config` runs, then `job.flags == ("-Xlinker", "-foo", "-Xlinker", "-bar")`.
- **Scenario 2 (Multi-glob `{stem}` & `depends-on`)**: Given glob job `"kernels"` (`input = "src/mo/*.mojo"`, `module = "pkg._{stem}"`) matching `a.mojo` and `b.mojo`, and job `"main"` with `depends-on = ["kernels"]`, when `plan_jobs` runs, then `"kernels[1]"` (`pkg._a.so`) and `"kernels[2]"` (`pkg._b.so`) precede `"main"` with `main.depends_on == ("kernels[1]", "kernels[2]")`.
- **Scenario 3 (Editable SDK-direct vs. ephemeral RPATH)**: Given `version == "editable"` and `bundle-libs = true`, when `modular_lib` is `/opt/modular/lib`, then `patch_editable_runtime` sets RPATH to `["/opt/modular/lib"]` without copying `.so` files; when `modular_lib` is under `tempfile.gettempdir()`, it stages `<build_dir>/editable.libs` and points RPATH there.
- **Scenario 4 (Incremental cache hit & invalidation)**: Given a compiled job with `cache = true`, when `compile_job` runs a second time without input/header/flag changes, then `mojo` is not invoked (`cache=hit` in log); when an imported `.mojo` file inside `include-dirs` changes, `mojo` recompiles and updates `cache.json`.

### 2.5 Alternatives Considered
- **Always copying `<pkg>.libs/` into the working tree on editable installs**: Rejected per Decision 3 because copying and patching 20–80 MB of SDK libraries on local dev builds slows iteration and dirties working trees when a persistent local SDK already exists on disk.
- **Timestamp-only (`st_mtime`) incremental build checks**: Rejected because Git branch switches and CI cache restores skew `mtime` values while SHA-256 content + flag + compiler digests are deterministic and fast across Mojo source trees.

## 3. Requirement-to-Task Traceability Matrix

| Requirement | Owning Task(s) | Verification Strategy | Confirmed Public Seam & Canonical Test Surface |
| --- | --- | --- | --- |
| R1 | `t01` | `regression_tdd` | `tests/test_config.py`, `tests/test_plugin.py` |
| R2 | `t02` | `regression_tdd` | `tests/test_planner.py`, `tests/test_config.py`, `tests/test_plugin.py` |
| R3 | `t03` | `behavior_tdd` | `tests/test_runtime.py`, `tests/test_plugin.py`, `tests/test_integration_wheel.py` |
| R4 | `t04` | `behavior_tdd` | `tests/test_compiler.py`, `tests/test_cleaning.py`, `tests/test_plugin.py`, `tests/test_integration_compile.py` |

## 4. Implementation Plan

### Phase 1: Config, Planner, Editable & Digest Cache Overhaul
- [x] [6c0e47f] t01 — Deep-merge profile sequences/dicts, tighten `jobs`/`install` validation, and add `skip-editable=false` & `cache=true` defaults (tasks/t01-config-schema-and-profile-merging.md)
- [x] [6616de5] t02 — Add `pathspec` glob filtering, `{stem}` multi-input outputs, and expanded `depends-on` DAG edges (tasks/t02-planner-globs-and-dag-edges.md)
- [x] [9b6a300] t03 — Implement `patch_editable_runtime`, `build_config`-aware editable placement, and `fail-fast = false` filtering (tasks/t03-editable-install-and-fail-fast.md)
- [x] [5731ab7] t04 — Add thread-safe SHA-256 `cache.json` incremental compilation and cleanup integration (tasks/t04-digest-build-cache.md)
- **Phase 1 Recovery Checkpoint**: `uv run ruff check . && uv run ruff format --check . && uv run mypy && uv run pyright && uv run slotscheck hatch_mojo && uv run pytest -q`

## 5. Continuity Snapshot
- **Flow ID**: `editable-planner-and-caching` (`state: completed`, `plan_revision: 3`, `plan_commit: ad4930f`)
- **Current Task**: `null`
- **Last Verified Checkpoint**: `5731ab7`
- **Key Decisions**:
  - `skip-editable` defaults to `false` with `HATCH_MOJO_SKIP_EDITABLE` override; editable RPATHs point directly to persistent `modular_lib` and fall back to `<build_dir>/editable.libs` when `_is_ephemeral_sdk` matches `tempfile.gettempdir()`, `builds-v0`, `.tmp*`, or `pip-build-env-*`.
  - `flags` concatenate verbatim across profiles without `set()` deduplication so repeated `-Xlinker` pairs remain intact.
- **Recent Discoveries**:
  - `pathspec` is guaranteed present as a direct runtime dependency of `hatchling`, enabling zero-extra-dependency `GitIgnoreSpec` glob evaluation on Python `3.10`+.
