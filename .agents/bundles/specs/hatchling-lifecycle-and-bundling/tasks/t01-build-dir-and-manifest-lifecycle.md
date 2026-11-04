---
type: Task
id: hatchling-lifecycle-and-bundling:t01
title: "Propagate config.build_dir, prune manifest directories, and move clean-after-build to MojoBuildHook.finalize"
description: "Use config.build_dir in planner defaults, isolate editable-manifest.json with empty-dir pruning, and run clean-after-build in MojoBuildHook.finalize for standard builds."
state: completed
priority: P1
verification_strategy: regression_tdd
depends_on: []
files:
  - hatch_mojo/planner.py
  - hatch_mojo/cleaning.py
  - hatch_mojo/plugin.py
tests:
  - tests/test_planner.py
  - tests/test_cleaning.py
  - tests/test_plugin.py
  - tests/test_integration_wheel.py
plan_revision: 3
plan_commit: 325c734
state_revision: 2
claimed_by: agent:executor
claimed_at: 2026-11-04T18:38:00Z
blocked_reason: null
unblock_condition: null
next_step: null
last_verified_at: 2026-11-04T18:47:09Z
last_verified_commit: 9f4663f
verification_evidence: "uv run pytest tests/test_planner.py tests/test_cleaning.py tests/test_plugin.py tests/test_integration_wheel.py -q (31 passed); ruff/mypy/pyright/slotscheck exit 0"
created_at: 2026-11-04T05:03:00Z
updated_at: 2026-11-04T18:47:09Z
commit: 9f4663f
tags: [bugfix, hatchling, lifecycle, cleaning, planner]
---

# Task `t01`: Propagate `config.build_dir`, Prune Manifest Directories, and Move `clean-after-build` to `MojoBuildHook.finalize`

## Objective

Honor `config.build_dir` in `planner._default_output`, track all staged/copied files with empty-directory pruning in `cleaning.py`, and move `clean-after-build` execution from `MojoBuildHook.initialize` to `MojoBuildHook.finalize` so wheel archiving never fails with missing forced-include files.

## Context

- **Verification Strategy (`regression_tdd`)**: Reproduces both the custom `build-dir` path mismatch and the fatal `uv build --wheel` `FileNotFoundError` when `clean-after-build = true`, then fixes them across `planner.py`, `cleaning.py`, and `plugin.py`.
- **Hatchling Lifecycle Contract**: `BuilderInterface.build` runs `initialize(version, build_data)` &rarr; `WheelBuilder.build_standard(...)` (reading `force_include` files from disk) &rarr; `finalize(version, build_data, artifact_path)`.
- **Canonical Test Targets**: `tests/test_planner.py`, `tests/test_cleaning.py`, `tests/test_plugin.py`, `tests/test_integration_wheel.py`.

## Steps

1. **Write failing regression tests (`RED`)**:
   - In `tests/test_planner.py`: add `test_custom_build_dir_default_output` verifying `build-dir = "build/custom_mojo"` places both `python-extension` (`build/custom_mojo/mogemma/_core.so`) and non-extension outputs under `tmp_path / "build/custom_mojo"`.
   - In `tests/test_cleaning.py`: add `test_clean_from_manifest_prunes_empty_build_dirs` verifying nested directories (`build/mojo/pkg.libs/libFoo.so` and `build/mojo/pkg/_core.so`) and `build/mojo` itself are removed when empty after unlinking tracked files while non-empty sibling directories survive, and `test_editable_manifest_isolated_from_standard_clean` verifying `clean_from_manifest(root, build_dir, include_editable=False)` preserves `editable-manifest.json` targets while `include_editable=True` removes both.
   - In `tests/test_plugin.py`: update `test_initialize_serial_path` so `initialize()` calls `clean_from_manifest` only once (`clean_before_build`), add `test_finalize_runs_clean_when_clean_after_build_enabled`, `test_finalize_skips_editable_even_when_clean_after_build_enabled`, and `test_finalize_noop_when_clean_after_build_disabled`, and verify `save_manifest` records bundled library paths in `manifest.json` while editable copy paths are recorded in `editable-manifest.json` (`MojoBuildHook.clean` passes `include_editable=True`).
   - In `tests/test_integration_wheel.py`: add `test_wheel_build_with_clean_after_build_and_custom_build_dir` running `uv build --wheel` with `build-dir = "build/custom_mojo"` and `clean-after-build = true`, asserting `my_pkg/_core.so` exists inside the built `.whl` and `project_dir / "build/custom_mojo"` no longer exists post-build.
2. **Implement `build_dir` propagation, directory pruning, and `finalize()` (`GREEN`)**:
   - In `hatch_mojo/planner.py::_default_output`: add parameter `build_dir: str` (`_default_output(root: Path, build_dir: str, job: JobConfig, input_path: Path) -> Path`) using `root / build_dir / ...` and pass `config.build_dir` from `_expand_all_jobs`.
   - In `hatch_mojo/cleaning.py`: retain `MANIFEST_NAME = "manifest.json"` and add `EDITABLE_MANIFEST_NAME = "editable-manifest.json"`; extend `manifest_path(root: Path, build_dir: str, *, filename: str = MANIFEST_NAME) -> Path` and `save_manifest(root: Path, build_dir: str, outputs: list[Path], *, filename: str = MANIFEST_NAME) -> Path` deduplicating sorted paths; parameterize `clean_from_manifest(root: Path, build_dir: str, *, include_editable: bool = False) -> None` unlinking tracked files from `manifest.json` (and `editable-manifest.json` when `include_editable=True`), unlinking the processed manifest file(s), and walking subdirectories under `root / build_dir` bottom-up (`sorted(..., reverse=True)` plus `root / build_dir`), calling `rmdir()` on empty directories (`OSError` ignored when non-empty).
   - In `hatch_mojo/plugin.py`:
     - Have `_copy_editable_artifacts(root, jobs) -> list[Path]` return the list of written destination paths.
     - In `MojoBuildHook.initialize`: pass `include_editable=(version == "editable")` when `config.clean_before_build` runs; collect `manifest_files: list[Path] = [job.output_path for job in planned]`, extend with `[Path(p) for p in bundled]` when `bundle_libs` runs, save `save_manifest(root, config.build_dir, manifest_files)`; when `version == "editable"`, save `_copy_editable_artifacts(root, planned)` into `save_manifest(root, config.build_dir, editable_files, filename=EDITABLE_MANIFEST_NAME)`; and remove the trailing `if config.clean_after_build:` block.
     - Add `MojoBuildHook.finalize(self, version: str, build_data: dict[str, Any], artifact_path: str) -> None`: return early immediately if `version == "editable"`; parse `config = parse_config(self.config, target_name=self.target_name)`; if `config.jobs and config.clean_after_build`, call `clean_from_manifest(Path(self.root), config.build_dir, include_editable=False)`.
     - In `MojoBuildHook.clean`: call `clean_from_manifest(root, config.build_dir, include_editable=True)`.
3. **Refactor & verify**:
   - Confirm zero inline `#` restatement comments and run static checks and wheel integration tests.

## Verification

```bash
# Initial RED check
uv run pytest tests/test_planner.py tests/test_cleaning.py tests/test_plugin.py tests/test_integration_wheel.py -q

# Final GREEN + static gates (all must exit 0)
uv run ruff check . && uv run ruff format --check . && uv run mypy && uv run pyright && uv run slotscheck hatch_mojo
uv run pytest tests/test_planner.py tests/test_cleaning.py tests/test_plugin.py tests/test_integration_wheel.py -q
```

## Acceptance Criteria

- [x] `planner._default_output` uses `config.build_dir` rather than hardcoded `"build/mojo"` (`R1`).
- [x] `save_manifest` records compiled outputs, staged runtime files, and editable copies, and `clean_from_manifest` prunes empty directories under `build_dir` (`R1`).
- [x] `MojoBuildHook.finalize` executes `clean-after-build` after wheel archiving, and `uv build --wheel` succeeds with `clean-after-build = true` (`R1`).
- [x] `ruff`, `mypy`, `pyright`, `slotscheck`, and `pytest` exit `0`.

## Notes & Discoveries

- `uv build --wheel` caches local `file://` build-system dependencies across runs when the package version is unchanged; integration tests in `tests/test_integration_wheel.py` pass `--refresh-package hatch-mojo` so `uv` rebuilds `hatch-mojo` from the live working tree.
