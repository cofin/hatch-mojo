---
type: Task
id: hatchling-lifecycle-and-bundling:t04
title: "Extend bundle_runtime_libs (RuntimeBundleResult) to executable and shared-lib jobs across platlib and .data layouts"
description: "Introduce RuntimeBundleResult and bundle Modular runtime libraries with relative RPATHs for python-extension, shared-lib, and executable jobs across platlib and shared_data."
state: pending
priority: P1
verification_strategy: behavior_tdd
depends_on:
  - hatchling-lifecycle-and-bundling:t03
files:
  - hatch_mojo/types.py
  - hatch_mojo/runtime.py
  - hatch_mojo/plugin.py
tests:
  - tests/test_runtime.py
  - tests/test_plugin.py
  - tests/test_integration_wheel.py
plan_revision: 3
plan_commit: null
state_revision: 0
claimed_by: null
claimed_at: null
blocked_reason: null
unblock_condition: null
next_step: null
last_verified_at: null
last_verified_commit: null
verification_evidence: null
created_at: 2026-11-04T05:03:00Z
updated_at: 2026-11-04T06:13:00Z
commit: null
tags: [feature, runtime, bundling, executable, rpath]
---

# Task `t04`: Extend `bundle_runtime_libs` (`RuntimeBundleResult`) to `executable` and `shared-lib` Jobs Across `platlib` and `.data` Layouts

## Objective

Introduce frozen slotted `RuntimeBundleResult` and extend `bundle_runtime_libs` to resolve, stage, license-annotate, and RPATH-patch Modular runtime libraries for `executable` and `shared-lib` jobs in addition to `python-extension` jobs across both `platlib` (`force_include`) and `.data` (`shared_data`) install schemes.

## Context

- **Verification Strategy (`behavior_tdd`)**: Expands `bundle_runtime_libs` from `python-extension`-only to all linkable native emits (`python-extension`, `shared-lib`, `executable`), leaving `object` and `mojoc` untouched.
- **Destination & RPATH Rules**:
  - **Platlib targets** (`emit == "python-extension"` or `install_kind in {"package", "root", "force-include"}`): stage into `<abs_build>/<libs_pkg>.libs/` mapped via `RuntimeBundleResult.force_include` to `<libs_pkg>.libs/<file>`, where `libs_pkg` is `job.module.split(".")[0]` (`python-extension`), `PurePosixPath(posixpath.normpath(resolve_install_target(job))).parts[0]` (`package`), or normalized `dist_name` (`re.sub(r"[-_.]+", "_", (dist_name or "").lower()).strip("_") or "mojo_runtime"` for `root`/`force-include`). Computing `parts = PurePosixPath(posixpath.normpath(resolve_install_target(job))).parts`, `depth = len(parts) - 1`; RPATH is `_compute_relative_rpath(depth, f"{libs_pkg}.libs")`.
  - **Data-scheme targets** (`install_kind in {"scripts", "data"}`): stage into `<abs_build>/shared/<libs_pkg>.libs/` mapped via `RuntimeBundleResult.shared_data` to `lib/<libs_pkg>.libs/<file>` (with `_write_license_notice(..., wheel_dir=f"lib/{libs_pkg}.libs")` installing notices at `<prefix>/lib/<libs_pkg>.libs/NOTICE.mojo-runtime`). Computing `parts = PurePosixPath(posixpath.normpath(resolve_install_target(job))).parts`, for `scripts` (`<prefix>/bin/<target>`) `depth = len(parts)` (`1` for `"my-cli"` &rarr; `$ORIGIN/../lib/<libs_pkg>.libs`; `2` for `"sub/my-cli"` &rarr; `$ORIGIN/../../lib/<libs_pkg>.libs`), and for `data` (`<prefix>/<target>`) `depth = len(parts) - 1` &rarr; `_compute_relative_rpath(depth, f"lib/{libs_pkg}.libs")`.
- **Canonical Test Targets**: `tests/test_runtime.py`, `tests/test_plugin.py`, `tests/test_integration_wheel.py`.

## Steps

1. **Write failing unit and wheel integration tests (`RED`)**:
   - In `tests/test_runtime.py`:
     - Update existing `bundle_runtime_libs` callers to inspect `result.force_include` / `result.shared_data` / `result.staged_files` on `RuntimeBundleResult`, and update `test_bundle_skips_no_ext_jobs` to use `emit="object"` and `emit="mojoc"` (since `shared-lib` is now bundled).
     - Add `test_get_linked_libraries_ldd_not_found_soname` verifying `"\tlibAsyncRTMojoBindings.so => not found"` lines in `ldd` stdout are captured so re-bundling pre-patched ELF binaries resolves all `modular_lib` dependencies.
     - Add tests verifying Linux (`patchelf`) and macOS (`install_name_tool` + `codesign`) bundling (including `dist_name=None` fallback to `"mojo_runtime"` and `-id @rpath/libfoo.dylib` on Darwin `shared-lib` jobs) for:
       1. `emit="executable"`, `install_kind="scripts"`, `install_path="my-cli"`, `dist_name="My-Pkg"` &rarr; stages in `result.shared_data` under `"lib/my_pkg.libs/..."` (including `"lib/my_pkg.libs/NOTICE.mojo-runtime"`) and sets binary RPATH to `["$ORIGIN", "$ORIGIN/../lib/my_pkg.libs"]` (`@loader_path` on Darwin), plus nested `install_path="sub/my-cli"` &rarr; `"$ORIGIN/../../lib/my_pkg.libs"` and `install_kind="data"`, `install_path="share/sub/"` &rarr; `"$ORIGIN/../../lib/my_pkg.libs"`.
       2. `emit="shared-lib"`, `install_kind="package"`, `install_path="my_pkg/native"` &rarr; stages in `result.force_include` under `"my_pkg.libs/..."` and sets RPATH to `["$ORIGIN", "$ORIGIN/../../my_pkg.libs"]` (and calls `-id @rpath/<name>` on Darwin).
       3. `emit="shared-lib"`, `install_kind="root"`, `install_path="libfoo.so"`, `dist_name=None` &rarr; stages in `result.force_include` under `"mojo_runtime.libs/..."` with depth-0 RPATH `["$ORIGIN", "$ORIGIN/mojo_runtime.libs"]`.
   - In `tests/test_plugin.py`: update all five `bundle_runtime_libs` monkeypatches (`test_initialize_serial_path`, `test_initialize_parallel_path`, `test_initialize_editable_copies_artifacts`, and both `_fake_bundle` helpers) to return `RuntimeBundleResult`, and verify `MojoBuildHook.initialize` merges `result.force_include` and `result.shared_data` into `build_data` and passes `result.staged_files` to `save_manifest`.
2. **Implement `RuntimeBundleResult` and full binary bundling (`GREEN`)**:
   - In `hatch_mojo/types.py`: add `@dataclass(slots=True, frozen=True) class RuntimeBundleResult` with `force_include: dict[str, str]`, `shared_data: dict[str, str]`, and `staged_files: tuple[Path, ...]`.
   - In `hatch_mojo/runtime.py`:
     - Add `_LDD_NOT_FOUND_RE: re.Pattern[str] = re.compile(r"^\s*(.+?)\s+=>\s+not found\b")` in `_get_linked_libraries` appending `m_nf.group(1)` so `DT_NEEDED` sonames in `modular_lib` always resolve.
     - Add keyword-optional `wheel_dir: str | None = None` (defaulting to `libs_dir.name`) to `_write_license_notice`, and add `set_install_id: bool = False` to `_patch_macos_extension` calling `_run_install_name_tool(["-id", f"@rpath/{ext.name}", str(ext)])` when `set_install_id` is `True` (`job.emit == "shared-lib"`).
     - Import `resolve_install_target` from `hatch_mojo.artifacts` and `RuntimeBundleResult` from `hatch_mojo.types`. Update `bundle_runtime_libs(root: Path, build_dir: str, jobs: list[BuildJob], mojo_bin: str | None, *, dist_name: str | None = None) -> RuntimeBundleResult` to partition linkable jobs (`emit in {"python-extension", "shared-lib", "executable"}`) into `platlib` groups and `shared_data` groups, stage libraries + notices per group (recording staged library and notice/license `Path`s in `staged_files`), patch Linux/macOS binaries, and return `RuntimeBundleResult`.
   - In `hatch_mojo/plugin.py`: resolve `dist_name` safely from `self.metadata.core.name` falling back to `self.metadata.name` inside `contextlib.suppress(AttributeError, ValueError)`, pass `dist_name=dist_name` to `bundle_runtime_libs`, merge `result.force_include` and `result.shared_data` (when non-empty) into `build_data`, and append `result.staged_files` to `manifest_files`.
3. **Refactor & verify**:
   - Run full Chapter 2 recovery checkpoint gates (`ruff`, `mypy`, `pyright`, `slotscheck`, and full `pytest`).

## Verification

```bash
# Initial RED check
uv run pytest tests/test_runtime.py tests/test_plugin.py -q

# Final GREEN + Chapter 2 Recovery Checkpoint (all must exit 0)
uv run ruff check . && uv run ruff format --check . && uv run mypy && uv run pyright && uv run slotscheck hatch_mojo
uv run pytest -q
```

## Acceptance Criteria

- [ ] `RuntimeBundleResult` is `@dataclass(slots=True, frozen=True)` and passes `slotscheck` (`R4`, `HBP-01`).
- [ ] `bundle_runtime_libs` stages and patches `python-extension`, `shared-lib`, and `executable` outputs across `platlib` (`force_include`) and `.data` (`shared_data`) layouts on Linux and macOS (`R4`, `NRB-01`..`NRB-07`).
- [ ] `object` and `mojoc` jobs are excluded from dynamic library bundling (`R4`).
- [ ] Full static analysis and `pytest` suite exit `0`.

## Notes & Discoveries

_None._
