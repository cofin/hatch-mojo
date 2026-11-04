---
type: Spec
flow_id: v0-2-overhaul
title: "hatch-mojo v0.2.0 Architectural Overhaul"
description: "Multi-flow roadmap modernizing hatch-mojo for Mojo 1.2+, Hatchling 1.33+, Apache-2.0 runtime bundling, zero-copy editable installs, digest caching, and py3-none wheel tagging."
state: completed
parent_prd: null
research:
  - research/mojo-packaging-landscape-audit_20261104.md
plan_revision: 3
plan_commit: 9782b0b
state_revision: 4
current_task: null
last_verified_checkpoint: 19d20d7
created_at: 2026-11-04T05:00:00Z
updated_at: 2026-11-04T20:38:00Z
tags: [migration, mojo, hatchling, packaging, v0-2-0]
---

# Master PRD: `hatch-mojo v0.2.0` Architectural Overhaul

## 1. North Star Goal & Problem Framing

### 1.1 Objectives
Deliver `hatch-mojo v0.2.0` so Python packages embedding Mojo extensions, shared libraries, CLI executables, or precompiled `.mojoc` packages build and install cleanly against **Mojo `1.2+` (`max==26.7+`)** and **Hatchling `1.33+`** across wheel and editable workflows without custom shell scripts.

### 1.2 Current State & Limits (`v0.1.8`)
`hatch-mojo` has not shipped since `v0.1.8` (`2026-03-07`, targeting Mojo `0.26.1`). Since then, Mojo reached `1.2.0`, decoupled its semantic versioning from MAX, removed `.mojopkg` in favor of `mojo precompile` (`.mojoc`), strictly validated `mojo build --emit` values (`exe` rather than `executable`; no `static-lib`), moved PyPI distribution from `modular` to `mojo-compiler` / `mojo`, and open-sourced the compiler and runtime under `Apache-2.0 WITH LLVM-exception`. Concurrently, `v0.1.8` contains internal Hatchling lifecycle bugs: `clean-after-build` deletes compiled outputs inside `MojoBuildHook.initialize` before `WheelBuilder` archives them, `planner._default_output` hardcodes `build/mojo`, `install.kind = "scripts" | "data"` writes into `site-packages/` instead of Hatchling's `shared_scripts`/`shared_data`, `bundle_runtime_libs` ignores `executable` and `shared-lib` jobs, editable installs fail at import time due to missing `<pkg>.libs` RPATH targets, and every build recompiles unconditionally without caching.

### 1.3 What Is New & Why It Succeeds
`hatch-mojo` remains the only dedicated Mojo wheel build plugin on PyPI (`pixi-build-mojo` targets `.conda` packages; `mohaus` replaces Hatchling off-PyPI without runtime `.libs` bundling; Modular's `mojo.importer` requires an ~80 MB runtime compiler and cannot pass `-I` include directories). Preserving the Hatchling `BuildHookInterface` plugin model and 6-module unidirectional pipeline while overhauling the toolchain, lifecycle, editable, caching, and wheel-tag seams aligns `hatch-mojo` with November 2026 standards, enables zero-install isolated PEP 517 builds via `mojo-compiler>=1.2.0` in `[build-system].requires`, and cuts consumer CI matrices up to 5x via opt-in `py3-none-<platform>` wheels.

### 1.4 Risks & Mitigations
- **Ephemeral PEP 517 SDK paths in editable builds**: When `mojo-compiler` is installed only in an ephemeral PEP 517 isolated build venv (`tempfile.gettempdir()` or `uv`'s `~/.cache/uv/builds-v0/.tmp*`), `uv`/`pip` deletes that venv after `build_editable` exits. Mitigation: detect ephemeral SDK paths (`tempfile.gettempdir()`, `builds-v0`, `.tmp*`, `pip-build-env-*`) and stage runtime libraries into persistent `<root>/<build_dir>/editable.libs` for editable RPATHs, while pointing directly at `modular_lib` for persistent local/Pixi/venv SDKs.
- **Free-threaded CPython (`cp313t`/`cp314t`) GIL re-enablement**: Mojo `1.2.0` dynamically loads `libpython` across CPython `3.10`–`3.14` without `Py_MOD_GIL_NOT_USED`. Mitigation: default `wheel-tag` (`"auto"`) keeps interpreter-specific `infer_tag = True` for `python-extension` wheels while defaulting standalone binary wheels to `py3-none-<platform>` and exposing explicit `wheel-tag = "py3-none"`.
- **Shared-script dynamic linking across install schemes**: Compiled CLI executables in `.data/scripts/` install to `<prefix>/bin/` rather than `platlib`. Mitigation: stage bundled runtime libraries for `scripts`/`data` jobs into `build_data["shared_data"]` (`lib/<dist>.libs/`) so `$ORIGIN/../lib/<dist>.libs` (`@loader_path/../lib/<dist>.libs`) resolves deterministically across virtualenvs, `uv tool`, and `--target` installs without a Python startup wrapper.

### 1.5 Success Metrics
1. `mojo build --emit exe|shared-lib|object` and `mojo precompile` (`.mojoc`) commands match Mojo `1.2.0` CLI contracts with zero invalid flags.
2. `discover_mojo` and `discover_modular_lib` locate binaries and `libKGENCompilerRTShared` across `mojo-compiler` / `mojo` PyPI wheels (`mojo._package_root`), external tool-venv console-script shims, Conda/Pixi prefixes, and `MODULAR_LIB_DIR`.
3. End-to-end `uv build --wheel` and editable installs succeed with `clean-after-build = true`, custom `build-dir`, `scripts`/`data` artifacts, digest build caching, and `wheel-tag = "py3-none"`.
4. `make check-all` passes with 100% `ruff`, `mypy --strict`, `pyright`, `slotscheck`, and `pytest` compliance across Linux, macOS, and Windows CI matrices (Python `3.10`–`3.15`).

## 2. Locked Architectural Seams & Alternatives Considered

### 2.1 Locked Cross-Cutting Decisions
1. **`EmitType` Contract (`hatch_mojo/types.py::EmitType`, `hatch_mojo/compiler.py::build_command`)**: `EmitType` is `Literal["python-extension", "shared-lib", "mojoc", "object", "executable"]`. `executable` maps to `mojo build --emit exe`; `mojoc` invokes `mojo precompile` emitting `.mojoc` archives without Mach-O linker flags; legacy `static-lib`, `.🔥`, and `.mojopkg` inputs fail fast in `parse_config` with actionable `ValueError` diagnostics.
2. **SDK Discovery & Apache-2.0 Attribution (`hatch_mojo/compiler.py::discover_mojo`, `hatch_mojo/runtime.py::discover_modular_lib`, `_write_license_notice`)**: Resolve `mojo._package_root`, `find_spec` across `("mojo", "mojo_compiler", "max", "modular")`, ancestor `lib/`, and external wrapper venv `site-packages/{modular,mojo,max}/lib`. Emit `Apache-2.0 WITH LLVM-exception` attribution in `NOTICE.mojo-runtime` (adding `MAX License` Section 1.5 notice only when MAX libraries are bundled), and keep Windows CI stub compatibility by inspecting `#!` shebang headers instead of blindly prepending `sys.executable`.
3. **Hatchling Lifecycle & Full Binary Bundling (`hatch_mojo/plugin.py::MojoBuildHook`, `hatch_mojo/artifacts.py::register_artifacts`, `hatch_mojo/runtime.py::bundle_runtime_libs`)**: Move `clean-after-build` to `MojoBuildHook.finalize` (skipping `editable` builds and isolating editable state in `editable-manifest.json` so standard cleanup never wipes active editable artifacts); pass `config.build_dir` to `planner._default_output`; route `scripts` &rarr; `build_data["shared_scripts"]` and `data` &rarr; `build_data["shared_data"]` (`hatchling>=1.31.0,!=1.32.3`, setting `bypass-selection` when no `force_include` exists); and extend runtime bundling + relative RPATHs to `executable` and `shared-lib` jobs (`shared_data` `lib/<dist>.libs/` for `.data/` targets, `force_include` `<pkg>.libs/` for `platlib` targets).
4. **Editable Installs, Planner Determinism & Digest Caching (`hatch_mojo/config.py`, `hatch_mojo/planner.py`, `hatch_mojo/compiler.py`)**: Default `skip-editable = false` (overridable via `HATCH_MOJO_SKIP_EDITABLE=1`); resolve editable package destinations from `build_config` raw `packages`/`sources` (copying package submodules into source packages and routing top-level/root artifacts via `force_include_editable` when `dev_mode_exact = true` or `force_include` otherwise) with persistent SDK-direct RPATHs (falling back to `<build_dir>/editable.libs` for ephemeral PEP 517 SDKs); deep-merge profile sequences/dicts; enforce `{stem}` templated targets on multi-file globs while expanding `depends-on` edges; filter failed jobs when `fail-fast = false`; and cache unpatched raw compiler outputs + SHA-256 digests in `<build_dir>/cache.json` (`cache = true` default).
5. **Wheel Tag Policy (`hatch_mojo/artifacts.py::register_artifacts`)**: Add `wheel-tag = "auto" | "infer" | "py3-none" | "<pep425_tag>"` (default `"auto"` &rarr; `"infer"` when `python-extension` jobs exist, `"py3-none"` when native jobs are exclusively standalone `executable`/`shared-lib`).

### 2.2 Alternatives Considered
- **Standalone Rust/Mojo PEP 517 Backend (Rewrite)**: Rejected because replacing Hatchling breaks existing `pyproject.toml` Hatch hook workflows (`hatch-vcs`, metadata hooks, multi-target builds) while providing negligible build-time savings relative to `mojo build`.
- **Emulating `static-lib` via `--emit object` + host `ar`**: Rejected because Mojo object files still depend on dynamic KGEN runtime symbols, making synthetic `.a` archives misleading without static KGEN libraries.
- **Defaulting all `python-extension` wheels to `py3-none-<platform>`**: Rejected as the default because free-threaded CPython (`cp313t`/`cp314t`) re-enables the GIL on Mojo extension import in `1.2.0`; keeping `"auto"` &rarr; `"infer"` for extensions and `"py3-none"` as an explicit 1-line opt-in balances safety with 5x CI matrix reduction.
- **Python `os.execv` trampoline scripts for bundled `scripts` executables**: Rejected in favor of staging `.data/` libraries via `build_data["shared_data"]` (`lib/<dist>.libs/`) with `$ORIGIN/../lib/<dist>.libs` RPATHs, preserving native zero-interpreter-overhead CLI startup.

## 3. Master Roadmap (Ordered Child Flows)

| Chapter | Flow ID | Title | Key Deliverables | Public Seams | Dependencies | State |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | `mojo-1-2-toolchain` | Mojo 1.2 Toolchain, Precompile & Apache-2.0 Runtime Discovery | `mojoc` (`mojo precompile`) emit, `--emit exe`, `mojo-compiler` / wrapper-venv SDK discovery, shebang-safe `win32` stub runner, `Apache-2.0 WITH LLVM-exception` notice | `parse_config`, `plan_jobs`, `discover_mojo`, `build_command`, `compile_job`, `discover_modular_lib`, `bundle_runtime_libs` | None | `completed` |
| 2 | `hatchling-lifecycle-and-bundling` | Hatchling 1.33 Lifecycle, Artifact Routing & Full Binary Bundling | `MojoBuildHook.finalize` cleanup, `config.build_dir` propagation, full manifest pruning, `shared_scripts`/`shared_data` routing, `executable`/`shared-lib` runtime bundling, Mach-O RPATH hardening | `MojoBuildHook.{initialize,finalize,clean}`, `register_artifacts`, `bundle_runtime_libs`, `save_manifest`, `clean_from_manifest` | `mojo-1-2-toolchain` | `completed` |
| 3 | `editable-planner-and-caching` | Editable Installs, Glob/DAG Planner Fixes & Digest Build Cache | `skip-editable = false` default, `force_include_editable` / package-aware editable RPATHs, profile list/dict merging, `{stem}` multi-glob & `depends-on` expansion, `fail-fast = false` filtering, SHA-256 `cache.json` | `parse_config`, `plan_jobs`, `plan_jobs_leveled`, `compile_job`, `patch_editable_runtime`, `MojoBuildHook.initialize` | `hatchling-lifecycle-and-bundling` | `completed` |
| 4 | `wheel-tags-metadata-and-ci` | Wheel Tag Policy, PEP 639 Metadata, Docs & Multi-OS CI | `wheel-tag` (`auto`/`infer`/`py3-none`/custom), PEP 639 `license = "MIT"` + `LICENSE`, `macos-latest` + Python `3.15` CI, Mojo `1.2` + `cibuildwheel 4.x` docs and skill sync | `parse_config`, `register_artifacts`, `pyproject.toml`, `.github/workflows/{ci,publish}.yml`, `README.md` | `editable-planner-and-caching` | `completed` |

## 4. Global Constraints (Applicable to All Child Flows)

- Target Python `>=3.10` with PEP 585 built-in generics (`list`, `dict`, `tuple`, `set`) and PEP 604 unions (`T | None`).
- Declare every dataclass in `hatch_mojo/` with `@dataclass(slots=True, frozen=True)` so `uv run slotscheck hatch_mojo` passes (`FP-HBP-01` exempts `MojoBuildHook`).
- Preserve unidirectional imports: lower modules (`types`, `config`, `planner`, `compiler`, `runtime`, `artifacts`, `cleaning`) never import `hatch_mojo.plugin` or `hatch_mojo.hooks`.
- Write zero inline `#` restatement comments in Python code; place rationale in Google-style docstrings.
- Place all tests in existing canonical 1:1 test files (`tests/test_<module>.py`, `tests/test_integration_*.py`) testing public seams without mocking the System Under Test.
- Never create or mutate Git tags, and never push or open PRs without explicit user instruction.

## 5. Backlog (Explicitly Out-of-Scope / Deferred Items)

- **Automatic `.pyi` stub generation from Mojo AST/docstrings**: Deferred until `mojo doc --json` stabilizes typed Python-binding export schemas across `PythonModuleBuilder` generics.
- **Native Windows (`win32`) PE/DLL import-table rewriting**: Deferred until Modular ships a native Windows Mojo SDK and runtime DLLs.
- **Cross-architecture cross-compilation linker orchestration**: Deferred because Mojo `1.2.0` omits a bundled cross-linker for `shared-lib`/`exe` targets.

## Implementation Plan

- [x] [67252d3] mojo-1-2-toolchain — Align compiler CLI (`exe`, `mojoc`), `mojo-compiler` SDK discovery, `win32` stub safety, and `Apache-2.0 WITH LLVM-exception` notices (../mojo-1-2-toolchain/spec.md)
- [x] [c694718] hatchling-lifecycle-and-bundling — Fix `finalize` cleanup, `build-dir`, `shared_scripts`/`shared_data` routing, and `executable`/`shared-lib` runtime bundling (../hatchling-lifecycle-and-bundling/spec.md)
- [x] [5731ab7] editable-planner-and-caching — Deliver zero-copy editable installs, profile/glob/DAG planner fixes, `fail-fast = false` filtering, and SHA-256 build caching (../editable-planner-and-caching/spec.md)
- [x] [19d20d7] wheel-tags-metadata-and-ci — Add `wheel-tag` (`auto`/`infer`/`py3-none`), PEP 639 metadata, `macos-latest` + Python `3.15` CI, and Mojo `1.2` documentation (../wheel-tags-metadata-and-ci/spec.md)

## Continuity Snapshot

- **Flow ID**: `v0-2-overhaul` (`state: completed`, `plan_revision: 3`, `plan_commit: 9782b0b`)
- **Current Task**: `null`
- **Last Verified Checkpoint**: `19d20d7`
- **Key Decisions**:
  - Replaced unsupported `static-lib` with `mojoc` (`mojo precompile`) and mapped `executable` &rarr; `--emit exe`.
  - Added `wheel-tag = "auto" | "infer" | "py3-none" | "<tag>"` defaulting to `"infer"` for `python-extension` and `"py3-none"` for standalone binaries.
  - Flipped `skip-editable` default to `false` (`HATCH_MOJO_SKIP_EDITABLE` override) using persistent SDK-direct RPATHs (with `<build_dir>/editable.libs` fallback for ephemeral `/tmp` and `uv` `builds-v0` PEP 517 SDK paths).
  - Extended runtime bundling to `executable` and `shared-lib` jobs while keeping cross-platform CI testability.
- **Recent Discoveries**:
  - Promoted `mojo-packaging-landscape-audit_20261104.md` establishing Mojo `1.2.0` (`max==26.7.0`), `Apache-2.0 WITH LLVM-exception`, `mojo-compiler` PyPI layout, and Hatchling `1.33.0` `WheelBuilder` contracts.
