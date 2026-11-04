# Bundle Changelog

## 2026-11-04

- `agent:flow-execution`: Implemented [`specs/hatchling-lifecycle-and-bundling/spec.md`](specs/hatchling-lifecycle-and-bundling/spec.md) (`9f4663f`..`c694718`: `t01`–`t04`) with Phase 1 Recovery Checkpoint verified across 144 passing `pytest` cases and clean `ruff`, `mypy`, `pyright`, and `slotscheck` gates.
- `agent:flow-execution`: Implemented [`specs/mojo-1-2-toolchain/spec.md`](specs/mojo-1-2-toolchain/spec.md) (`51de4cc`..`67252d3`: `t01`–`t04`) with Phase 1 Recovery Checkpoint verified across 126 passing `pytest` cases and clean `ruff`, `mypy`, `pyright`, and `slotscheck` gates.
- `agent:plan-generator`: Authored Master PRD [`specs/v0-2-overhaul/spec.md`](specs/v0-2-overhaul/spec.md), promoted [`specs/v0-2-overhaul/research/mojo-packaging-landscape-audit_20261104.md`](specs/v0-2-overhaul/research/mojo-packaging-landscape-audit_20261104.md), and expanded all 4 child flows (`mojo-1-2-toolchain`, `hatchling-lifecycle-and-bundling`, `editable-planner-and-caching`, `wheel-tags-metadata-and-ci`) into 15 zero-decision task worksheets.
- `agent:researcher`: Added open research audit [`specs/v0-2-overhaul/research/mojo-packaging-landscape-audit_20261104.md`](specs/v0-2-overhaul/research/mojo-packaging-landscape-audit_20261104.md) covering Mojo `0.26.2`–`1.2.0` (`max==26.7.0`), `Apache-2.0 WITH LLVM-exception` open-sourcing, November 2026 packaging tools (`mojo-compiler`, `pixi-build-mojo`, `mohaus`), Hatchling `1.33.0` / `cibuildwheel 4.3.5`, and `hatch-mojo v0.1.8` defects with a targeted `v0.2.0` overhaul recommendation.
- `agent:flow-setup`: Initialized OKF v0.2 bundle under `.agents/bundles/`, migrated context from legacy `.agent/`, contracted historical archived flows into `knowledge/{architecture,domains,patterns,testing,gotchas,decisions}/`, generated project-local skills (`hatch-build-pipeline`, `native-runtime-bundling`, `review-*`) and paired subagents, and retired legacy `.agent/` and `.beads/` trackers.

## 2026-03-08

- `human:cody`: Contracted `robust-macho-patching_20260308` — centralized macOS `install_name_tool` execution in `hatch_mojo/runtime.py::_run_install_name_tool` with `stderr` reporting and substring-based idempotency (`already contains LC_RPATH`, `no LC_RPATH found`), replacing brittle `otool -l` pre-check regexes.

## 2026-03-02

- `human:cody`: Contracted `dynamic-resolver_20260302` and `integrate-resolver_20260302` — replaced hardcoded runtime library lists in `hatch_mojo/runtime.py::bundle_runtime_libs` with recursive `ldd` / `otool -L` dependency walking (`_resolve_modular_dependencies`) bounded by `modular/lib` and `libKGENCompilerRTShared`.

## 2026-02-25

- `human:cody`: Contracted `change-build-dir`, `wheel-integration-test`, and `ci-matrix-expansion` — standardized default `build-dir` to `build/mojo`, added end-to-end `uv build --wheel` verification in `tests/test_integration_wheel.py`, and expanded CI matrix across Linux and Windows on Python 3.10–3.14.
