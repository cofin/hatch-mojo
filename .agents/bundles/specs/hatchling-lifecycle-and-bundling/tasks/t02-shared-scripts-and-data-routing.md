---
type: Task
id: hatchling-lifecycle-and-bundling:t02
title: "Route scripts and data jobs to Hatchling shared_scripts / shared_data and update dependency floors"
description: "Route scripts/data jobs via resolve_install_target, enable bypass-selection for zero-Python wheels, and upgrade Hatchling/packaging floors in pyproject.toml and uv.lock."
state: pending
priority: P1
verification_strategy: regression_tdd
depends_on:
  - hatchling-lifecycle-and-bundling:t01
files:
  - pyproject.toml
  - uv.lock
  - hatch_mojo/artifacts.py
  - hatch_mojo/plugin.py
tests:
  - tests/test_artifacts.py
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
updated_at: 2026-11-04T06:04:00Z
commit: null
tags: [bugfix, hatchling, artifacts, scripts, wheel]
---

# Task `t02`: Route `scripts` and `data` Jobs to Hatchling `shared_scripts` / `shared_data` and Update Dependency Floors

## Objective

Route `install.kind = "scripts"` and `"data"` into Hatchling's `build_data["shared_scripts"]` and `build_data["shared_data"]` maps via a canonical `resolve_install_target(job)` helper, and update `pyproject.toml` runtime dependency bounds to `hatchling>=1.31.0,!=1.32.3` and `packaging>=24.2`.

## Context

- **Verification Strategy (`regression_tdd`)**: Fixes the defect where `install = { kind = "scripts", path = "my-cli" }` placed binaries at `site-packages/my-cli/cli` instead of `<dist>-<ver>.data/scripts/my-cli` on `PATH`.
- **Why `hatchling>=1.31.0,!=1.32.3`**: Hatchling `1.31.0` fixed `WheelBuilder.add_shared_scripts` to rewrite only Python shebangs without corrupting native binary executables; `1.32.3` broke `BuildHookInterface[Any]` subscripting at import time.
- **Canonical Test Targets**: `tests/test_artifacts.py`, `tests/test_integration_wheel.py`.

## Steps

1. **Write failing unit and wheel integration tests (`RED`)**:
   - In `tests/test_artifacts.py`:
     - Update `test_register_non_python_variants` and add `test_register_scripts_and_data_use_shared_maps` asserting:
       - `install = { kind = "scripts", path = "my-cli" }` writes `build_data["shared_scripts"][str(bin_path)] == "my-cli"` (and `"sub/my-cli"` when `path = "sub/"` + `output_path.name == "my-cli"`), without adding `bin_path` to `build_data["force_include"]`.
       - `install = { kind = "data", path = "share" }` writes `build_data["shared_data"][str(data_path)] == "share/d.bin"`, while `path = "share/custom.dat"` writes `"share/custom.dat"`.
       - `force-include` trailing slash (`path = "lib/"`, `output_path.name = "lib.so"`) resolves to `"lib/lib.so"` while exact file path (`path = "custom/lib.so"`) resolves to `"custom/lib.so"`.
       - `resolve_install_target(job)` works identically even when `job.output_path` lies outside `root`.
   - In `tests/test_plugin.py`: add `test_initialize_sets_bypass_selection_for_standalone_shared_scripts` verifying `build_config.target_config["bypass-selection"]` is set to `True` when `shared_scripts`/`shared_data` is populated and `force_include` is empty, without overriding an explicit user `bypass-selection`.
   - In `tests/test_integration_wheel.py`: add `test_wheel_build_installs_executable_in_data_scripts` building a zero-Python standalone CLI project (no `src/` or `__init__.py`!) with `emit = "executable"` and `install = { kind = "scripts", path = "my-cli" }` via `uv build --wheel` and asserting `"my_pkg-1.0.0.data/scripts/my-cli"` is in `zf.namelist()` with intact binary bytes.
2. **Implement dependency floors, `shared_scripts`/`shared_data` routing, and `bypass-selection` (`GREEN`)**:
   - In `pyproject.toml`: set `[project] dependencies = ["hatchling>=1.31.0,!=1.32.3", "packaging>=24.2"]`, `[build-system] requires = ["hatchling>=1.31.0,!=1.32.3"]`, and append `"editables>=0.5"` to `[dependency-groups].test` (so Hatchling's `WheelBuilder.build_editable_detection` works in integration tests), then run `uv lock && uv sync --all-extras --dev` so `.venv` upgrades to `hatchling>=1.33.0` and `uv.lock` stays synchronized.
   - In `hatch_mojo/artifacts.py`:
     - Add public helper `resolve_install_target(job: BuildJob) -> str`:
       - For `emit == "python-extension"`: require `job.module` and return `_module_dest(job.module, job.output_path)`.
       - Require `job.install_kind` and (`job.install_kind == "root"` or `job.install_path`).
       - `root`: return `job.output_path.name`.
       - `force-include`: assert `job.install_path is not None`; if `job.install_path.endswith("/")`, return `f"{job.install_path.strip('/')}/{job.output_path.name}"`; else return `job.install_path.lstrip("/")`.
       - `package`: assert `job.install_path is not None`; return `f"{job.install_path.strip('/')}/{job.output_path.name}"`.
       - `scripts`: assert `job.install_path is not None`; if `job.install_path.endswith("/")`, return `f"{job.install_path.strip('/')}/{job.output_path.name}"`; else return `job.install_path.lstrip("/")`.
       - `data`: assert `job.install_path is not None`; `cleaned = job.install_path.lstrip("/")`; if `cleaned.endswith("/")` or (`"/" not in cleaned` and `"." not in Path(cleaned).name`), return `f"{cleaned.rstrip('/')}/{job.output_path.name}"`; else return `cleaned`.
     - In `register_artifacts`: route `scripts` to `build_data.setdefault("shared_scripts", {})[source] = target`, `data` to `build_data.setdefault("shared_data", {})[source] = target`, and `python-extension` / `force-include` / `package` / `root` to `build_data.setdefault("force_include", {})[source] = target`.
   - In `hatch_mojo/plugin.py::MojoBuildHook.initialize`: after artifact registration, if `(build_data.get("shared_scripts") or build_data.get("shared_data") or build_data.get("force_include_editable")) and not build_data.get("force_include")`, inspect `target_cfg = getattr(getattr(self, "build_config", None), "target_config", None)` and call `target_cfg.setdefault("bypass-selection", True)` when `isinstance(target_cfg, dict)` (note: Hatchling checks `<pkg>/__init__.py` before `bypass_selection`, so mixed Python+CLI projects remain unaffected while zero-Python CLI/editable wheels succeed cleanly).
3. **Refactor & verify**:
   - Confirm `uv.lock` and `.venv` match `pyproject.toml` and run all static and pytest gates.

## Verification

```bash
# Initial RED check
uv run pytest tests/test_artifacts.py tests/test_integration_wheel.py -q

# Final GREEN + static gates (all must exit 0)
uv run ruff check . && uv run ruff format --check . && uv run mypy && uv run pyright && uv run slotscheck hatch_mojo
uv run pytest tests/test_artifacts.py tests/test_integration_wheel.py -q
```

## Acceptance Criteria

- [ ] `pyproject.toml` specifies `dependencies = ["hatchling>=1.31.0,!=1.32.3", "packaging>=24.2"]` (`R2`).
- [ ] `register_artifacts` routes `scripts` to `build_data["shared_scripts"]` and `data` to `build_data["shared_data"]`, placing CLI executables at `<dist>-<ver>.data/scripts/<name>` (`R2`).
- [ ] `resolve_install_target(job)` handles paths outside `root` without `ValueError` (`R2`).
- [ ] `ruff`, `mypy`, `pyright`, `slotscheck`, and focused `pytest` modules exit `0`.

## Notes & Discoveries

_None._
