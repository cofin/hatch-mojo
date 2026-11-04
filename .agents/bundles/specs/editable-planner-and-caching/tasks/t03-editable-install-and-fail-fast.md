---
type: Task
id: editable-planner-and-caching:t03
title: "Implement patch_editable_runtime, build_config-aware editable placement, and fail-fast = false filtering"
description: "Place editable artifacts cleanly across .pth and dev_mode_exact modes, patch editable RPATHs without mutating build_dir outputs, and filter fail-fast=false failures."
state: pending
priority: P1
verification_strategy: behavior_tdd
depends_on:
  - editable-planner-and-caching:t02
files:
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
created_at: 2026-11-04T05:05:00Z
updated_at: 2026-11-04T06:04:00Z
commit: null
tags: [feature, editable, rpath, fail-fast, hatchling]
---

# Task `t03`: Implement `patch_editable_runtime`, `build_config`-Aware Editable Placement, and `fail-fast = false` Filtering

## Objective

Make editable installs (`version == "editable"`) work reliably via persistent SDK-direct RPATHs (falling back to `<build_dir>/editable.libs` when `modular_lib` is under `tempfile.gettempdir()`), `build_config.packages`/`dev_mode_exact`-aware artifact placement without duplicate `force_include` wheel pollution, and safe `fail-fast = false` failed-job filtering.

## Context

- **Verification Strategy (`behavior_tdd` + `regression_tdd`)**: Introduces `patch_editable_runtime` and `dev_mode_exact` `force_include_editable` routing while fixing `fail-fast = false` downstream crashes.
- **Editable RPATH Persistence Rule (`_is_ephemeral_sdk`)**: Treat `modular_lib` as ephemeral (`False` if `resolved.is_relative_to(root.resolve())`) when `resolved.is_relative_to(Path(tempfile.gettempdir()).resolve())` OR any segment in `resolved.parts` equals `"builds-v0"` or starts with `(".tmp", "pip-build-env-", "build-env-")` (covering both `/tmp` PEP 517 build envs and `uv`'s `~/.cache/uv/builds-v0/.tmp*` isolated build envs!). Always copy editable binaries to their editable destination paths (`src/<pkg>/_core.so` or `<build_dir>/editable/<name>`) *before* calling `patch_editable_runtime` on those copies so `<build_dir>` compiler outputs remain unmutated.
- **Canonical Test Targets**: `tests/test_runtime.py`, `tests/test_plugin.py`, `tests/test_integration_wheel.py`.

## Steps

1. **Write failing unit and integration tests (`RED`)**:
   - In `tests/test_runtime.py`:
     - Add `test_patch_editable_runtime_persistent_sdk_linux` and `test_patch_editable_runtime_persistent_sdk_darwin` (with `modular_lib` inside `root / ".venv/modular/lib"`) verifying RPATH on target binaries is patched directly to `[str(modular_lib.resolve())]` (plus `@rpath/<lib>` rewrite + `_strip_absolute_rpaths` + `codesign` on Darwin) and returns `()` with zero copied `.libs` files.
     - Add `test_patch_editable_runtime_ephemeral_sdk_linux_and_darwin` covering both an external `tempfile` path AND a simulated `<home>/.cache/uv/builds-v0/.tmpAbCdEf/.../modular/lib` path, verifying libraries + `NOTICE.mojo-runtime` stage into `<root>/<build_dir>/editable.libs/` with `stat.S_IWUSR`, sibling dylib relocation (`patchelf --set-rpath $ORIGIN` on Linux; `_patch_macos_dylibs` + `codesign` on Darwin), target RPATH `[str((root / build_dir / "editable.libs").resolve())]`, and staged paths returned.
   - In `tests/test_plugin.py`:
     - Add `test_initialize_fail_fast_false_filters_failed_and_dependent_jobs` verifying a failed job in serial or parallel mode logs a warning and is excluded from `bundle_runtime_libs`, `register_artifacts`, and `save_manifest` (returning cleanly if all jobs fail).
     - Update editable tests and add `test_initialize_editable_uses_raw_target_config_packages_without_force_include` and `test_initialize_editable_dev_mode_exact_copies_submodules_and_preserves_force_include` verifying: (a) dotted package extensions (`my_pkg._core`) copy into custom `target_config = {"packages": ["python/my_pkg"]}` in both `.pth` and `dev_mode_exact = True` modes without triggering premature `WheelBuilderConfig` property evaluation or duplicating into `force_include`; (b) top-level extensions (`module = "_core"`) and `root`/`force-include` artifacts route to `force_include_editable` (preserving existing `build_config.get_force_include()` entries) when `dev_mode_exact = True` and `force_include` when `False`; and (c) `<build_dir>` compiler outputs are not mutated in place by `patch_editable_runtime`.
   - In `tests/test_integration_wheel.py`: add `test_editable_wheel_build_succeeds_by_default` invoking `WheelBuilder(str(project_dir)).build(directory=str(dist_dir), versions=["editable"])` (`from hatchling.builders.wheel import WheelBuilder`, using `editables>=0.5` added in `hatchling-lifecycle-and-bundling:t02` and `bundle-libs = false` with the `fake_mojo` stub) on a sample project without setting `skip-editable` in `pyproject.toml`, verifying `_core.so` is placed in `src/my_pkg/_core.so` and NOT duplicated inside the `.whl` archive's `my_pkg/_core.so` (which contains `_my_pkg.pth` instead).
2. **Implement `patch_editable_runtime`, editable placement, and `fail-fast = false` filtering (`GREEN`)**:
   - In `hatch_mojo/runtime.py`: extract shared library staging (`stat.S_IWUSR`, Linux `patchelf --set-rpath $ORIGIN` / Darwin `_patch_macos_dylibs`, and `_write_license_notice`) and implement `_is_ephemeral_sdk(modular_lib: Path, root: Path) -> bool` and `patch_editable_runtime(root: Path, build_dir: str, jobs: list[BuildJob], mojo_bin: str | None) -> tuple[Path, ...]` patching each `job.output_path` on Linux (`patchelf`) and macOS (`_strip_absolute_rpaths`, `-change`, `-add_rpath`, `_resign_ad_hoc`, plus `-id @rpath/<name>` on `shared-lib`).
   - In `hatch_mojo/plugin.py`:
     - Add `_resolve_editable_package_dirs(root: Path, build_config: Any) -> dict[str, Path]` reading raw `"packages"` and `"sources"` from `build_config.target_config` / `build_config.build_config` dicts first (falling back to `getattr(build_config, "packages", None)` only when `target_config` is absent on `SimpleNamespace` stubs) before `_SOURCE_LAYOUTS`.
     - Track `failed_names: set[str]` across serial/level execution; skip jobs whose `depends_on` intersects `failed_names` (calling `self.app.display_warning`), and keep only `succeeded: list[BuildJob]`. Return early if `not succeeded`.
     - Branch `version == "editable"` vs standard wheel: copy dotted `python-extension` (`"." in job.module`) and `install.kind == "package"` outputs into resolved local package dirs, stage remaining editable outputs (`module` without `"."`, `root`, `force-include`, `scripts`, `data`) into `<root>/<config.build_dir>/editable/`, construct `editable_jobs = [dataclasses.replace(job, output_path=dest) ...]` and run `patch_editable_runtime(root, config.build_dir, editable_jobs, mojo_bin)` when `config.bundle_libs` is `True`, register uncopied `platlib` jobs in `force_include_editable` (seeded from `build_config.get_force_include()` when `dev_mode_exact = True`) or `force_include` (when `dev_mode_exact = False`) plus `shared_scripts`/`shared_data` (keeping `force_include_editable` in the zero-Python `bypass-selection` check), and save all editable copies + `editable.libs` in `EDITABLE_MANIFEST_NAME`.
3. **Refactor & verify**:
   - Run all static checks and `test_runtime`, `test_plugin`, and `test_integration_wheel`.

## Verification

```bash
# Initial RED check
uv run pytest tests/test_runtime.py tests/test_plugin.py tests/test_integration_wheel.py -q

# Final GREEN + static gates (all must exit 0)
uv run ruff check . && uv run ruff format --check . && uv run mypy && uv run pyright && uv run slotscheck hatch_mojo
uv run pytest tests/test_runtime.py tests/test_plugin.py tests/test_integration_wheel.py -q
```

## Acceptance Criteria

- [ ] `patch_editable_runtime` embeds persistent `modular_lib` RPATHs directly without copying libraries, and stages `<build_dir>/editable.libs` when `modular_lib` resides in an external tempdir (`R3`).
- [ ] Editable installs resolve custom `build_config.packages` layouts, support `dev_mode_exact` via `force_include_editable`, and avoid duplicating source-copied `.so` files into `site-packages` (`R3`).
- [ ] `fail-fast = false` filters failed jobs and their dependents before runtime bundling and artifact registration (`R3`).
- [ ] `ruff`, `mypy`, `pyright`, `slotscheck`, and focused `pytest` modules exit `0`.

## Notes & Discoveries

_None._
