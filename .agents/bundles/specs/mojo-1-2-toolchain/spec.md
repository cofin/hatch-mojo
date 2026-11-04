---
type: Spec
flow_id: mojo-1-2-toolchain
title: "Mojo 1.2 Toolchain, Precompile & Apache-2.0 Runtime Discovery"
description: "Align emit types, compiler CLI flags, mojo-compiler SDK discovery, Windows test stub handling, and runtime license notices with Mojo 1.2+."
state: completed
parent_prd: v0-2-overhaul
research:
  - ../v0-2-overhaul/research/mojo-packaging-landscape-audit_20261104.md
plan_revision: 3
plan_commit: 9782b0b
state_revision: 5
current_task: null
last_verified_checkpoint: 67252d3
created_at: 2026-11-04T05:01:00Z
updated_at: 2026-11-04T18:35:00Z
tags: [migration, mojo, compiler, runtime, licensing]
---

# Flow: Mojo 1.2 Toolchain, Precompile & Apache-2.0 Runtime Discovery

## 1. Specification & Context

### 1.1 Problem Statement & Objectives
`hatch-mojo v0.1.8` targets Mojo `0.26.1` CLI, packaging, and legal conventions that broke across Mojo `0.26.2`–`1.2.0`:
1. `hatch_mojo/compiler.py::build_command` passes `--emit executable` (rejected by Mojo `1.2.0`, which strictly requires `--emit exe`) and exposes `emit = "static-lib"` (unsupported by `mojo build`), while lacking `mojo precompile` (`.mojoc`) support after `.mojopkg` removal.
2. `hatch_mojo/compiler.py::discover_mojo` and `hatch_mojo/runtime.py::discover_modular_lib` probe legacy `modular` imports and 5-level binary ancestors, failing when `mojo-compiler>=1.2.0` or `mojo>=1.2.0` is installed in an isolated PEP 517 build environment (`mojo._package_root`) or invoked via an external tool-venv console-script wrapper (`<venv>/bin/mojo` &rarr; `<venv>/lib/python3.X/site-packages/modular/lib`).
3. `hatch_mojo/compiler.py::compile_job` blindly prefixes `sys.executable` on `win32` whenever `command[0]` lacks `.exe`, attempting to execute `.cmd`/`.bat` shims or `PATH` commands as Python scripts, while `discover_mojo` ignores `.venv/Scripts/`.
4. `hatch_mojo/runtime.py::_MOJO_RUNTIME_NOTICE` cites the retired *Modular Community License* (`max-mojo-license`) instead of `Apache-2.0 WITH LLVM-exception` (and `MAX License` Section 1.5 when MAX libraries are bundled), and writes notices without explicit `encoding="utf-8"`.

**Objectives**: Align `EmitType` and CLI generation with Mojo `1.2.0`, discover binaries and runtime libraries across `mojo-compiler`/`mojo`/`max`/Conda/wrapper-venv layouts, restrict `win32` `sys.executable` wrapping to `#!`-shebang scripts, and emit accurate `Apache-2.0 WITH LLVM-exception` runtime notices.

**Non-Goals**: Hatchling `finalize` cleanup, `shared_scripts`/`shared_data` routing, non-extension runtime bundling, editable RPATH patching, digest caching, and `wheel-tag` policy (owned by Chapters 2–4).

### 1.2 Upstream Execution Baseline
- **Branch**: `main`
- **Parent PRD**: [`v0-2-overhaul`](../v0-2-overhaul/spec.md) (Chapter 1 of 4; no upstream child-flow dependencies)

### 1.3 Code Analysis & Seam Summary

| Area | Files Examined (`path/to/file::Symbol`) | Public Seam, Dependency Category & Integration |
| --- | --- | --- |
| Domain Types | `hatch_mojo/types.py::EmitType`, `EMIT_VALUES`, `BuildJob` | In-process frozen types consumed by all pipeline stages. |
| Config Validation | `hatch_mojo/config.py::_validate_job`, `parse_config` | In-process TOML schema validation rejecting removed Mojo `0.x` artifacts/emits. |
| Output Suffixes | `hatch_mojo/planner.py::_get_suffix_map` | Local-substitutable planner mapping `EmitType` to OS file suffixes. |
| Compiler Discovery & CLI | `hatch_mojo/compiler.py::discover_mojo`, `build_command`, `compile_job` | External boundary building `mojo build` / `mojo precompile` argv and running subprocesses. |
| SDK & Notice Bundling | `hatch_mojo/runtime.py::discover_modular_lib`, `_MOJO_RUNTIME_NOTICE`, `_write_license_notice` | External/FS boundary locating `libKGENCompilerRTShared` and emitting license notices. |

### 1.4 Relevant Patterns, Domain Terms & Knowledge Chapters
- Architecture & Domain: [`build-pipeline-seams.md`](../../knowledge/architecture/build-pipeline-seams.md), [`mojo-wheel-packaging.md`](../../knowledge/domains/mojo-wheel-packaging.md)
- Patterns & Testing: [`typed-slotted-models.md`](../../knowledge/patterns/typed-slotted-models.md), [`public-seam-verification.md`](../../knowledge/testing/public-seam-verification.md), [`platform-linking-and-build-quirks.md`](../../knowledge/gotchas/platform-linking-and-build-quirks.md)
- Project Skills: [`hatch-build-pipeline`](../../../skills/hatch-build-pipeline/SKILL.md), [`native-runtime-bundling`](../../../skills/native-runtime-bundling/SKILL.md)

## 2. Requirements & Architecture

### 2.1 Functional Requirements
- **R1 (`EmitType`, Mojo `1.2` CLI & `.gitignore` Spec Unblocking)**: Anchor `.gitignore` line 2 from `specs` to `/specs` so `.agents/bundles/specs/**` is trackable from Task 1 onward; replace `"static-lib"` with `"mojoc"` in `EmitType` and `EMIT_VALUES`; reject `emit = "static-lib"` and `.🔥` / `📦` / `.mojopkg` paths in `parse_config` with actionable `ValueError` messages; map `"executable"` to `mojo build --emit exe`; and map `"mojoc"` to `mojo precompile` producing `.mojoc` outputs without `--emit` or Darwin `-headerpad_max_install_names` linker flags.
- **R2 (Out-of-Tree Path Safety in `build_command`)**: Format `job.input_path` and `job.output_path` in `build_command` relative to `root` when `path.is_relative_to(root)`, falling back to `str(path)` when outside `root` so external output/staging paths never raise `ValueError`.
- **R3 (`mojo-compiler` Binary Discovery & Shebang-Safe `win32` Execution)**: Extend `discover_mojo` to probe `mojo._package_root` (`get_package_root() / "bin" / "mojo"`, guarding `None` returns) and `win32` `.venv/Scripts/mojo.{exe,cmd,bat}`; in `compile_job`, resolve `shutil.which` on `win32` and prepend `sys.executable` only when `command[0]` is an existing file starting with `b"#!"`; update Mojo source snippets in `tests/test_integration_*.py` to Mojo `1.x` syntax (`def` / `std.python.bindings`).
- **R4 (Modern SDK Library Discovery)**: Extend `discover_modular_lib` in strict compiler-matched order: `MODULAR_LIB_DIR` &rarr; `mojo_bin` ancestors and `<venv>/{lib/python*/site-packages,lib64/python*/site-packages,lib/python*/dist-packages,Lib/site-packages}/{modular,mojo,mojo_compiler,max}/lib` (when `mojo_bin` is provided) &rarr; `mojo._package_root` &rarr; `importlib.util.find_spec` across `("mojo", "mojo_compiler", "max", "modular")` (including sibling `site-packages/modular/lib`) &rarr; `$CONDA_PREFIX/lib`, `/opt/modular/lib`, `<root>/.pixi/envs/default/lib`, and `<root>/.modular/lib`.
- **R5 (`Apache-2.0 WITH LLVM-exception` Runtime Notice)**: Update `_MOJO_RUNTIME_NOTICE` and `_write_license_notice` to cite `Apache License 2.0 with LLVM Exceptions` (`https://github.com/modular/modular/blob/main/LICENSE`, `Copyright (c) Modular Inc, a Qualcomm Company`), append a `MAX License` Section 1.5 paragraph (`https://www.modular.com/legal/max-license`) only when MAX libraries (`libMAX*`, `libMOGG*`) are present in `lib_filenames`, write `NOTICE.mojo-runtime` with `encoding="utf-8"`, and copy SDK `LICENSE` files (applying `stat.S_IWUSR`) from `modular_lib.parent / "LICENSE"` or matching `mojo*.dist-info` / `modular*.dist-info` / `max*.dist-info` directories.

### 2.2 Public Interfaces, Deep Modules & Seam Contracts
- `hatch_mojo/types.py::EmitType = Literal["python-extension", "shared-lib", "mojoc", "object", "executable"]`
- `hatch_mojo/compiler.py::build_command(mojo_bin: str, root: Path, job: BuildJob) -> list[str]`:
  - When `job.emit == "mojoc"`: `[mojo_bin, "precompile", *(-I <d>), *(-D <k>), *job.flags, <input_arg>, "-o", <output_arg>]`.
  - Otherwise: `[mojo_bin, "build", "--emit", emit_map[job.emit], *(-I <d>), *(-D <k>), *(darwin headerpad if linkable), *job.flags, <input_arg>, "-o", <output_arg>]` where `emit_map = {"python-extension": "shared-lib", "shared-lib": "shared-lib", "object": "object", "executable": "exe"}`.
- `hatch_mojo/compiler.py::discover_mojo(root: Path, configured: str | None) -> str`:
  - Priority: `configured` &rarr; `os.getenv("HATCH_MOJO_BIN")` &rarr; `_discover_mojo_from_package()` (`mojo._package_root`) &rarr; `shutil.which("mojo")` &rarr; local `.venv` (`Scripts/mojo.{exe,cmd,bat}` on `win32`, `bin/mojo` on POSIX).
- `hatch_mojo/runtime.py::discover_modular_lib(root: Path, mojo_bin: str | None) -> Path`:
  - Validates every candidate against `(candidate / _sentinel()).exists()` and raises `FileNotFoundError` referencing `MODULAR_LIB_DIR` and `mojo-compiler>=1.2.0`.

### 2.3 Non-Functional & Safety Constraints
- Preserve `@dataclass(slots=True, frozen=True)`, PEP 585/604 types, Google-style docstrings, and zero inline `#` restatement comments.
- Do not import `mojo` eagerly at module import time; probe `mojo._package_root` lazily via `importlib` inside discovery functions.

### 2.4 Acceptance Scenarios (Given / When / Then)
- **Scenario 1 (`executable` CLI)**: Given a `BuildJob` with `emit="executable"`, when `build_command("mojo", root, job)` runs, then argv starts with `["mojo", "build", "--emit", "exe"]` (including `-Xlinker -headerpad_max_install_names` on `darwin`).
- **Scenario 2 (`mojoc` precompile)**: Given a job with `emit="mojoc"` in `parse_config`, when `plan_jobs` and `build_command` run, then `output_path` ends with `.mojoc` and argv starts with `["mojo", "precompile"]` without `--emit` or `-headerpad_max_install_names`.
- **Scenario 3 (Removed Mojo `0.x` artifacts)**: Given `emit = "static-lib"` or `input = "src/core.🔥"` or `output = "pkg.mojopkg"`, when `parse_config` runs, then `ValueError` is raised naming the unsupported Mojo `0.x` construct.
- **Scenario 4 (External tool-venv wrapper discovery)**: Given an isolated build where `find_spec` returns `None` and `mojo_bin` points to `<tmp>/tool-venv/bin/mojo` while `libKGENCompilerRTShared.so` lives at `<tmp>/tool-venv/lib/python3.12/site-packages/modular/lib/`, when `discover_modular_lib(root, mojo_bin)` runs, then that `modular/lib` path is returned.
- **Scenario 5 (Apache-2.0 notice)**: Given bundled `["libKGENCompilerRTShared.so"]`, when `_write_license_notice` runs, then `NOTICE.mojo-runtime` is UTF-8 encoded, cites `Apache License 2.0 with LLVM Exceptions` and `Modular Inc, a Qualcomm Company`, and omits `Modular Community License`.

### 2.5 Alternatives Considered
- **Drop `static-lib` without adding `mojoc`**: Rejected per Decision 1 because supporting `mojo precompile` lets wheels ship reusable `.mojoc` packages alongside Python wrappers behind the same job DAG.
- **Synthesize `.a` archives via `--emit object` + `ar rcs`**: Rejected because Mojo `.o` outputs still require dynamic KGEN runtime symbols, making static archives unusable without the Mojo shared runtime.
- **Keep unconditional `win32` `[sys.executable, *command]` prefixing**: Rejected because real `.cmd`/`.bat` shims or `PATH` commands fail when passed to `python.exe`; inspecting the 2-byte `#!` header isolates test-script execution cleanly.

## 3. Requirement-to-Task Traceability Matrix

| Requirement | Owning Task(s) | Verification Strategy | Confirmed Public Seam & Canonical Test Surface |
| --- | --- | --- | --- |
| R1 | `t01` | `behavior_tdd` | `tests/test_config.py`, `tests/test_planner.py`, `tests/test_compiler.py`, `tests/test_artifacts.py` |
| R2 | `t01` | `regression_tdd` | `tests/test_compiler.py::test_build_command_outside_root_paths` |
| R3 | `t02` | `regression_tdd` | `tests/test_compiler.py`, `tests/test_integration_compile.py`, `tests/test_integration_wheel.py` |
| R4 | `t03` | `behavior_tdd` | `tests/test_runtime.py` (`discover_modular_lib` suite) |
| R5 | `t04` | `behavior_tdd` | `tests/test_runtime.py` (`_write_license_notice` & `bundle_runtime_libs` suite) |

## 4. Implementation Plan

### Phase 1: Mojo 1.2 CLI, Discovery & Licensing Alignment
- [x] [51de4cc] t01 — Align `EmitType`, `mojoc` precompile CLI, and Mojo `0.x` input validation (tasks/t01-emit-types-and-cli.md)
- [x] [95de96e] t02 — Add `mojo._package_root` & `.venv/Scripts` binary discovery and shebang-safe `win32` execution (tasks/t02-mojo-discovery-and-win32-cleanup.md)
- [x] [0465180] t03 — Expand `discover_modular_lib` for `mojo-compiler`, wrapper venvs, and Conda/Pixi prefixes (tasks/t03-sdk-lib-discovery.md)
- [x] [67252d3] t04 — Migrate `NOTICE.mojo-runtime` to `Apache-2.0 WITH LLVM-exception` and UTF-8 SDK license copying (tasks/t04-apache-license-notice.md)
- **Phase 1 Recovery Checkpoint**: `uv run ruff check . && uv run ruff format --check . && uv run mypy && uv run pyright && uv run slotscheck hatch_mojo && uv run pytest -q`

## 5. Continuity Snapshot
- **Flow ID**: `mojo-1-2-toolchain` (`state: completed`, `plan_revision: 3`, `plan_commit: 9782b0b`)
- **Current Task**: `null`
- **Last Verified Checkpoint**: `67252d3`
- **Key Decisions**:
  - `EmitType` replaces `"static-lib"` with `"mojoc"` (`mojo precompile`) and maps `"executable"` &rarr; `mojo build --emit exe`.
  - `win32` script wrapping checks `b"#!"` file magic rather than blindly wrapping non-`.exe` commands.
  - `NOTICE.mojo-runtime` cites `Apache-2.0 WITH LLVM-exception` with conditional `MAX License` Section 1.5 text when MAX libraries are bundled.
- **Recent Discoveries**:
  - `tests/test_artifacts.py::test_register_non_python_variants` contains a `"static-lib"` fixture literal that `t01` updates to `"mojoc"` so strict `mypy` passes across `hatch_mojo` and `tests`.
