# Bundle Changelog

## 2026-11-04

- `agent:flow-setup`: Initialized OKF v0.2 bundle under `.agents/bundles/`, migrated context from legacy `.agent/`, contracted historical archived flows into `knowledge/{architecture,domains,patterns,testing,gotchas,decisions}/`, generated project-local skills (`hatch-build-pipeline`, `native-runtime-bundling`, `review-*`) and paired subagents, and retired legacy `.agent/` and `.beads/` trackers.

## 2026-03-08

- `human:cody`: Contracted `robust-macho-patching_20260308` — centralized macOS `install_name_tool` execution in `hatch_mojo/runtime.py::_run_install_name_tool` with `stderr` reporting and substring-based idempotency (`already contains LC_RPATH`, `no LC_RPATH found`), replacing brittle `otool -l` pre-check regexes.

## 2026-03-02

- `human:cody`: Contracted `dynamic-resolver_20260302` and `integrate-resolver_20260302` — replaced hardcoded runtime library lists in `hatch_mojo/runtime.py::bundle_runtime_libs` with recursive `ldd` / `otool -L` dependency walking (`_resolve_modular_dependencies`) bounded by `modular/lib` and `libKGENCompilerRTShared`.

## 2026-02-25

- `human:cody`: Contracted `change-build-dir`, `wheel-integration-test`, and `ci-matrix-expansion` — standardized default `build-dir` to `build/mojo`, added end-to-end `uv build --wheel` verification in `tests/test_integration_wheel.py`, and expanded CI matrix across Linux and Windows on Python 3.10–3.14.
