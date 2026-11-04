---
type: Spec
flow_id: hatchling-lifecycle-and-bundling
title: "Hatchling 1.33 Lifecycle, Artifact Routing & Full Binary Bundling"
description: "Fix MojoBuildHook.finalize cleanup, build-dir propagation, shared_scripts/shared_data routing, Mach-O RPATH stripping, and executable/shared-lib runtime bundling."
state: completed
parent_prd: v0-2-overhaul
research:
  - ../v0-2-overhaul/research/mojo-packaging-landscape-audit_20261104.md
plan_revision: 3
plan_commit: 325c734
state_revision: 5
current_task: null
last_verified_checkpoint: c694718
created_at: 2026-11-04T05:03:00Z
updated_at: 2026-11-04T19:35:00Z
tags: [bugfix, hatchling, lifecycle, artifacts, runtime]
---

# Flow: Hatchling 1.33 Lifecycle, Artifact Routing & Full Binary Bundling

## 1. Specification & Context

### 1.1 Problem Statement & Objectives
`hatch-mojo v0.1.8` violates several Hatchling `WheelBuilder` contracts and leaves non-extension binaries unbundled:
1. `MojoBuildHook.initialize` calls `clean_from_manifest` when `clean-after-build = true` *before* Hatchling archives `build_data["force_include"]`, causing `WheelBuilder` (`BuilderInterface.recurse_forced_files`) to fail with `FileNotFoundError("Forced include not found: ...")`.
2. `planner._default_output` hardcodes `root / "build/mojo"` instead of `config.build_dir`, and `cleaning.py` tracks only compiled job outputs—orphaning `<pkg>.libs/`, `NOTICE`/`LICENSE` files, and empty directories.
3. `artifacts.register_artifacts` maps `install.kind = "scripts"` and `"data"` into `build_data["force_include"]` (`site-packages/my-cli/cli`) instead of Hatchling's `build_data["shared_scripts"]` (`<prefix>/bin/my-cli` on `PATH`, binary-safe since `hatchling 1.31.0`) and `build_data["shared_data"]`.
4. `runtime._compute_extension_rpath` emits malformed `"$ORIGIN//pkg.libs"` when module depth is `0`, `_strip_absolute_rpaths` matches `"path "` outside `LC_RPATH` blocks and is omitted on macOS extensions, and `bundle_runtime_libs` skips `executable` and `shared-lib` jobs completely.

**Objectives**: Align cleanup with `MojoBuildHook.finalize`, propagate `config.build_dir` end-to-end, route `scripts`/`data` to `shared_scripts`/`shared_data` (`hatchling>=1.31.0,!=1.32.3`), harden Mach-O RPATH stripping, and bundle runtime libraries with exact relative RPATHs across `python-extension`, `shared-lib`, and `executable` jobs.

**Non-Goals**: Editable install RPATH strategy, profile sequence merging, glob `{stem}` / DAG expansion, digest caching, and `wheel-tag` overrides (owned by Chapters 3–4).

### 1.2 Upstream Execution Baseline
- **Branch**: `main`
- **Parent PRD**: [`v0-2-overhaul`](../v0-2-overhaul/spec.md) (Chapter 2 of 4)
- **Prerequisite Child Flow**: [`mojo-1-2-toolchain`](../mojo-1-2-toolchain/spec.md)

### 1.3 Code Analysis & Seam Summary

| Area | Files Examined (`path/to/file::Symbol`) | Public Seam, Dependency Category & Integration |
| --- | --- | --- |
| Hook Lifecycle | `hatch_mojo/plugin.py::MojoBuildHook.{initialize,finalize,clean}` | Host adapter (`BuildHookInterface`) orchestrating pre-archive build and post-archive cleanup. |
| Default Outputs | `hatch_mojo/planner.py::_default_output`, `_expand_all_jobs` | Local-substitutable path planner honoring `config.build_dir`. |
| Manifest Cleanup | `hatch_mojo/cleaning.py::save_manifest`, `clean_from_manifest` | Local-substitutable JSON manifest tracking all staged files and pruning empty `build_dir` directories. |
| Wheel Inclusion | `hatch_mojo/artifacts.py::register_artifacts` | In-process mapper populating `force_include`, `shared_scripts`, `shared_data`, and purity flags. |
| Runtime Bundler | `hatch_mojo/runtime.py::bundle_runtime_libs`, `_strip_absolute_rpaths`, `hatch_mojo/types.py::RuntimeBundleResult` | External/FS boundary staging `platlib` (`force_include`) and `.data` (`shared_data`) runtime libraries and patching ELF/Mach-O RPATHs. |

### 1.4 Relevant Patterns, Domain Terms & Knowledge Chapters
- Architecture & Domain: [`build-pipeline-seams.md`](../../knowledge/architecture/build-pipeline-seams.md), [`mojo-wheel-packaging.md`](../../knowledge/domains/mojo-wheel-packaging.md)
- Patterns & Decisions: [`typed-slotted-models.md`](../../knowledge/patterns/typed-slotted-models.md), [`idempotent-binary-patching.md`](../../knowledge/patterns/idempotent-binary-patching.md), [`adr-001`](../../knowledge/decisions/adr-001-dynamic-runtime-dependency-resolution.md), [`adr-002`](../../knowledge/decisions/adr-002-idempotent-macho-rpath-patching.md)
- Project Skills: [`hatch-build-pipeline`](../../../skills/hatch-build-pipeline/SKILL.md), [`native-runtime-bundling`](../../../skills/native-runtime-bundling/SKILL.md)

## 2. Requirements & Architecture

### 2.1 Functional Requirements
- **R1 (`build-dir` Propagation, Isolated Editable Manifest & `finalize` Cleanup)**: `planner._default_output` places default outputs under `root / config.build_dir / ...`; `save_manifest` records compiled outputs, staged runtime libraries, and license notices in `manifest.json` for standard builds while isolating editable copies in `editable-manifest.json`; `clean_from_manifest(root, build_dir, *, include_editable=False)` unlinks tracked files and prunes empty directories inside `root / build_dir` (cleaning `editable-manifest.json` only when `include_editable=True` in `MojoBuildHook.clean` or editable `clean-before-build`); and `clean-after-build = true` executes inside `MojoBuildHook.finalize(version, build_data, artifact_path)` only when `version != "editable"` so live editable `.so` artifacts are never deleted post-build.
- **R2 (`shared_scripts`, `shared_data` & Zero-Python `bypass-selection` Routing)**: Bump `pyproject.toml` `[project].dependencies` to `["hatchling>=1.31.0,!=1.32.3", "packaging>=24.2"]` and `[build-system].requires` to `["hatchling>=1.31.0,!=1.32.3"]` (syncing `uv.lock` and `.venv` to `hatchling>=1.33.0`); route `install.kind == "scripts"` to `build_data["shared_scripts"][source] = target` and `install.kind == "data"` to `build_data["shared_data"][source] = target` (supporting trailing `/` directory semantics across `force-include`, `scripts`, and `data`); and set `target_config.setdefault("bypass-selection", True)` in `MojoBuildHook.initialize` whenever `(shared_scripts or shared_data) and not force_include` so standalone zero-`.py` CLI/data wheels succeed without `WheelBuilderConfig` file-selection errors.
- **R3 (Depth-0 RPATH, Scoped Mach-O RPATH Stripping & `_patch_rpath` Re-Signing)**: Fix `_compute_relative_rpath(depth: int, libs_rel_dir: str)` so depth `0` emits `[origin, f"{origin}/{libs_rel_dir}"]` without double slashes; scope `_strip_absolute_rpaths` strictly to `cmd LC_RPATH` blocks in `otool -l`; call `_strip_absolute_rpaths(ext)` inside `_patch_macos_extension`; and call `_resign_ad_hoc(target)` at the end of `_patch_rpath` on `darwin`.
- **R4 (Runtime Bundling for `executable` & `shared-lib` Jobs)**: Introduce `@dataclass(slots=True, frozen=True) class RuntimeBundleResult` (`force_include: dict[str, str]`, `shared_data: dict[str, str]`, `staged_files: tuple[Path, ...]`) returned by `bundle_runtime_libs(root, build_dir, jobs, mojo_bin, *, dist_name: str | None = None)`. Match `ldd` `"=> not found"` sonames in `_get_linked_libraries` so re-bundling pre-patched ELF binaries remains idempotent; normalize `dist_name` safely when `None` (`(dist_name or "").lower()`); bundle transitive `modular/lib` dependencies across `python-extension`, `shared-lib`, and `executable` jobs (`platlib` in `<build_dir>/<libs_pkg>.libs/` via `force_include`, `.data` in `<build_dir>/shared/<libs_pkg>.libs/` via `shared_data` under `lib/<libs_pkg>.libs/` with `NOTICE.mojo-runtime` under matching `wheel_dir`, `PurePosixPath` depth math, and `-id @rpath/<name>` on macOS `shared-lib` outputs).

### 2.2 Public Interfaces, Deep Modules & Seam Contracts
- `hatch_mojo/types.py::RuntimeBundleResult`:
  ```python
  @dataclass(slots=True, frozen=True)
  class RuntimeBundleResult:
      """Staged runtime library mappings for Hatch wheel inclusion."""

      force_include: dict[str, str]
      shared_data: dict[str, str]
      staged_files: tuple[Path, ...]
  ```
- `hatch_mojo/artifacts.py`: Expose pure helper `resolve_install_target(job: BuildJob) -> str` used by both `register_artifacts` and `runtime.py` so `scripts`, `data`, `package`, `root`, and `force-include` destination path depths are computed from a single source of truth.
- `hatch_mojo/plugin.py::MojoBuildHook.finalize(self, version: str, build_data: dict[str, Any], artifact_path: str) -> None`: Runs `clean_from_manifest(Path(self.root), config.build_dir)` when `version != "editable"`, `config.clean_after_build` is `True`, and `bool(config.jobs)`.

### 2.3 Non-Functional & Safety Constraints
- Every Mach-O binary modified with `install_name_tool` (`dylib`, `python-extension`, `shared-lib`, `executable`) must strip residual absolute `LC_RPATH`s, apply `stat.S_IWUSR` on staged copies, route through `_run_install_name_tool`, and finish with `_resign_ad_hoc` (`NRB-01`..`NRB-05`).
- `RuntimeBundleResult` must use `@dataclass(slots=True, frozen=True)` so `uv run slotscheck hatch_mojo` passes (`HBP-01`).

### 2.4 Acceptance Scenarios (Given / When / Then)
- **Scenario 1 (`clean-after-build` wheel integrity)**: Given `clean-after-build = true` and `build-dir = "build/custom"` in `pyproject.toml`, when `uv build --wheel` runs, then the resulting `.whl` archive contains `my_pkg/_core.so` and `build/custom` is removed after `finalize()` completes.
- **Scenario 2 (`scripts` CLI installation path)**: Given `emit = "executable"` with `install = { kind = "scripts", path = "my-cli" }`, when `uv build --wheel` runs, then the wheel contains `my_pkg-1.0.0.data/scripts/my-cli` rather than `my_pkg/my-cli/cli`.
- **Scenario 3 (Scoped Mach-O RPATH stripping)**: Given `otool -l` output containing `cmd LC_ID_DYLIB` (`name /opt/modular/lib/libFoo.dylib`) and `cmd LC_RPATH` (`path /opt/modular/lib (offset 12)`), when `_strip_absolute_rpaths` runs on an extension or dylib, then `-delete_rpath /opt/modular/lib` is called only for `LC_RPATH` entries.
- **Scenario 4 (`scripts` executable runtime bundling)**: Given an `executable` job with `install = { kind = "scripts", path = "my-cli" }` and `bundle-libs = true` for `dist_name = "my-pkg"`, when `bundle_runtime_libs` runs on Linux, then libraries stage in `shared_data` under `lib/my_pkg.libs/` and `patchelf --set-rpath` receives `$ORIGIN:$ORIGIN/../lib/my_pkg.libs`.

### 2.5 Alternatives Considered
- **Mutating `build_data` directly inside `runtime.py`**: Rejected because keeping `runtime.py` decoupled from Hatchling's `build_data` dict via `RuntimeBundleResult` preserves testable value-object boundaries (`build-pipeline-seams.md`).
- **Generating `#!python` `os.execv` wrapper scripts for `scripts` executables**: Rejected because staging libraries via `build_data["shared_data"]` (`lib/<dist>.libs/`) gives `<prefix>/bin/<cli>` a deterministic `$ORIGIN/../lib/<dist>.libs` RPATH across POSIX virtualenvs and `--target` prefixes with zero Python startup overhead.

## 3. Requirement-to-Task Traceability Matrix

| Requirement | Owning Task(s) | Verification Strategy | Confirmed Public Seam & Canonical Test Surface |
| --- | --- | --- | --- |
| R1 | `t01` | `regression_tdd` | `tests/test_planner.py`, `tests/test_cleaning.py`, `tests/test_plugin.py`, `tests/test_integration_wheel.py` |
| R2 | `t02` | `regression_tdd` | `tests/test_artifacts.py`, `tests/test_plugin.py`, `tests/test_integration_wheel.py` |
| R3 | `t03` | `regression_tdd` | `tests/test_runtime.py` |
| R4 | `t04` | `behavior_tdd` | `tests/test_runtime.py`, `tests/test_plugin.py`, `tests/test_integration_wheel.py` |

## 4. Implementation Plan

### Phase 1: Hatchling Lifecycle, Routing & Full Binary Bundling
- [x] [9f4663f] t01 — Propagate `config.build_dir`, prune manifest directories, and move `clean-after-build` to `MojoBuildHook.finalize` (tasks/t01-build-dir-and-manifest-lifecycle.md)
- [x] [25e92d4] t02 — Route `scripts` and `data` jobs to Hatchling `shared_scripts` / `shared_data` and update dependency floors (tasks/t02-shared-scripts-and-data-routing.md)
- [x] [0219211] t03 — Fix depth-0 RPATH formatting and scope macOS `_strip_absolute_rpaths` to `LC_RPATH` across dylibs and extensions (tasks/t03-macos-rpath-and-top-level-hardening.md)
- [x] [c694718] t04 — Extend `bundle_runtime_libs` (`RuntimeBundleResult`) to `executable` and `shared-lib` jobs across `platlib` and `.data` layouts (tasks/t04-non-extension-runtime-bundling.md)
- **Phase 1 Recovery Checkpoint**: `uv run ruff check . && uv run ruff format --check . && uv run mypy && uv run pyright && uv run slotscheck hatch_mojo && uv run pytest -q`

## 5. Continuity Snapshot
- **Flow ID**: `hatchling-lifecycle-and-bundling` (`state: completed`, `plan_revision: 3`, `plan_commit: 325c734`)
- **Current Task**: `null`
- **Last Verified Checkpoint**: `c694718`
- **Key Decisions**:
  - `MojoBuildHook.finalize` owns `clean-after-build` execution after `WheelBuilder` finishes archiving.
  - `RuntimeBundleResult` separates `force_include` (`platlib`) and `shared_data` (`<prefix>/lib/<dist>.libs/`) cleanly without leaking `build_data` into `runtime.py`.
- **Recent Discoveries**:
  - Hatchling `1.31.0` fixed `WheelBuilder.add_shared_scripts` to rewrite only `#!.*python` headers, preserving native ELF/Mach-O executables verbatim; `hatchling==1.32.3` broke `BuildHookInterface[Any]` and must be excluded in `pyproject.toml`.
