---
type: Guide
title: Public-Seam Verification and Test Map
description: Canonical 1:1 test file mapping, dependency boundary rules, synthetic wheel integration harnesses, and tight repro commands.
status: stable
tags: [testing, tdd, pytest]
generated:
  by: flow/0.26.0
  at: 2026-11-04T03:56:00Z
verified:
  - by: agent:flow-setup
    at: 2026-11-04T03:56:00Z
    commit: 1b6d139
sources:
  - id: test-wheel
    resource: tests/test_integration_wheel.py::test_wheel_build_includes_native_extension
    title: End-to-end uv build --wheel integration test using synthetic mojo script
  - id: test-compile
    resource: tests/test_integration_compile.py::test_compile_job_creates_output
    title: Subprocess compile_job integration test using executable fake mojo script
  - id: test-runtime
    resource: tests/test_runtime.py::test_bundle_full_flow
    title: Runtime bundling tests mocking only OS binary boundaries and sys.platform
  - id: test-planner
    resource: tests/test_planner.py::test_plan_jobs_leveled_mixed_deps
    title: Public-seam planner tests using real tmp_path trees
---

# Public-Seam Verification and Test Map

<!-- truth: start -->
- Place every unit test in the canonical 1:1 test file matching the module under test (`hatch_mojo/<module>.py` &rarr; `tests/test_<module>.py`) and end-to-end packaging tests in `tests/test_integration_compile.py` or `tests/test_integration_wheel.py`[^test-wheel][^test-compile].
- Never create standalone `test_*remediation*.py` or `test_*audit*.py` files, never mock the System Under Test, and never write tautological assertions that recompute production formulas.
- Use real `tmp_path` directory trees and real `parse_config` / `BuildJob` instances for `config`, `planner`, `artifacts`, and `cleaning` tests[^test-planner].
- Mock or monkeypatch **only** external OS/process boundaries (`subprocess.run` for `ldd`, `otool`, `patchelf`, `install_name_tool`, `codesign`; `sys.platform`; `shutil.which`; `importlib.util.find_spec`) so Linux, macOS, and Windows code paths execute deterministically on any CI host without requiring the proprietary Modular SDK[^test-runtime].
<!-- truth: end -->

## Canonical Module-to-Test Map

| Source Module | Canonical Test File | Dependency Strategy |
| --- | --- | --- |
| `hatch_mojo/hooks.py` | `tests/test_hooks.py` | Direct in-process call (`hatch_register_build_hook() is MojoBuildHook`). |
| `hatch_mojo/config.py` | `tests/test_config.py` | Pure in-process `parse_config` calls asserting `HookConfig` outputs and validation errors. |
| `hatch_mojo/planner.py` | `tests/test_planner.py` | Real `tmp_path` `.mojo` files + `plan_jobs` / `plan_jobs_leveled`; `monkeypatch` `sys.platform` only for cross-OS suffix checks[^test-planner]. |
| `hatch_mojo/compiler.py` | `tests/test_compiler.py`, `tests/test_integration_compile.py` | Direct `build_command` / `discover_mojo` checks + real `subprocess.run` against synthetic executable `mojo` Python scripts[^test-compile]. |
| `hatch_mojo/artifacts.py` | `tests/test_artifacts.py` | Direct `register_artifacts` against in-memory `build_data` dicts and `tmp_path` files. |
| `hatch_mojo/cleaning.py` | `tests/test_cleaning.py` | Real `save_manifest` / `clean_from_manifest` round-trips in `tmp_path`. |
| `hatch_mojo/runtime.py` | `tests/test_runtime.py` | Real `tmp_path` staged binaries and `NOTICE`/`LICENSE` files; `patch` on `subprocess.run` (`ldd`, `otool`, `patchelf`, `install_name_tool`, `codesign`) and `sys.platform`[^test-runtime]. |
| `hatch_mojo/plugin.py` | `tests/test_plugin.py`, `tests/test_integration_wheel.py` | Orchestration seam tests in `test_plugin.py` + real `uv build --wheel` zip inspection in `test_integration_wheel.py`[^test-wheel]. |

## Tight Red-Capable Bug Diagnosis Pattern

Before proposing any bug fix, construct and run a single fast (<1s) failing `pytest` invocation targeting the exact public seam:

```bash
uv run pytest tests/test_runtime.py -k "test_<repro_name>" -vv
```

For end-to-end Hatchling hook regressions, reproduce inside `tests/test_integration_wheel.py` using `_write_fake_mojo`, `uv build --wheel`, and `zipfile.ZipFile(wheel_path).namelist()` assertions[^test-wheel].

## Provenance

[^test-wheel]: `tests/test_integration_wheel.py::test_wheel_build_includes_native_extension` — Exercises `uv build --wheel` with `hatch-mojo @ file://...` and inspects resulting `.whl` archive entries.
[^test-compile]: `tests/test_integration_compile.py::test_compile_job_creates_output` — Runs `compile_job` against an executable Python stub emulating `mojo build -o`.
[^test-runtime]: `tests/test_runtime.py::test_bundle_full_flow` — Exercises `bundle_runtime_libs` across Linux, macOS, and Windows with simulated `ldd`/`otool` outputs.
[^test-planner]: `tests/test_planner.py::test_plan_jobs_leveled_mixed_deps` — Verifies topological level grouping and glob expansion against `tmp_path`.
