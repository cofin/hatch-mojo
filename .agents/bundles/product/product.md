---
type: Guide
title: Product Definition
description: Problem statement, target users, and build-hook capabilities of hatch-mojo.
status: stable
tags: [hatch, mojo, packaging]
generated:
  by: flow/0.26.0
  at: 2026-11-04T03:54:00Z
verified:
  - by: agent:flow-setup
    at: 2026-11-04T03:54:00Z
    commit: 1b6d139
sources:
  - id: pyproject-entry
    resource: pyproject.toml
    title: Hatch entry-point declaration and package metadata
  - id: hook-entry
    resource: hatch_mojo/hooks.py::hatch_register_build_hook
    title: Hatchling build hook registration entry point
  - id: plugin-hook
    resource: hatch_mojo/plugin.py::MojoBuildHook
    title: Core MojoBuildHook lifecycle implementation
  - id: runtime-bundler
    resource: hatch_mojo/runtime.py::bundle_runtime_libs
    title: Mojo runtime library discovery, bundling, and RPATH patching
---

# Product Definition

<!-- truth: start -->
- `hatch-mojo` registers the `mojo` build hook (`hatch_mojo.hooks`) with Hatchling (`BuildHookInterface`) to compile `.mojo` sources during Python package builds[^pyproject-entry][^hook-entry].
- Primary users are Python package maintainers shipping compiled Mojo Python extension modules (`.so` / `.pyd`) or native binaries (shared libraries, static libraries, objects, executables) inside standard wheels[^plugin-hook].
- All build behavior is configured declaratively under `[tool.hatch.build.targets.<target>.hooks.mojo]` in `pyproject.toml` (profiles, globbed jobs, platform/arch/PEP 508 markers, and topological `depends-on` ordering).
- When `bundle-libs = true` (default), `hatch-mojo` resolves linked Modular SDK runtime libraries, stages them into `<pkg>.libs/` with `NOTICE.mojo-runtime`, and rewrites ELF/Mach-O RPATHs for self-contained Linux and macOS wheels[^runtime-bundler].
<!-- truth: end -->

## Problem & Target Users

Python packages embedding Mojo extensions otherwise require bespoke shell scripts to invoke `mojo build`, map outputs into Hatchling's `build_data`, rewrite dynamic linker paths (`patchelf` / `install_name_tool`), re-sign Mach-O binaries on Apple Silicon, and satisfy Modular runtime redistribution notice requirements. `hatch-mojo` encapsulates those steps behind Hatchling's standard build hook lifecycle (`MojoBuildHook.initialize` and `MojoBuildHook.clean`)[^plugin-hook].

## Core Capabilities

1. **Declarative Compilation Pipeline**: Validates `profiles` and `jobs` from `pyproject.toml`, filters jobs by Hatch target, globs, `sys.platform`, `platform.machine()`, and PEP 508 markers, and compiles sequentially or in level-parallel `ThreadPoolExecutor` waves respecting `depends-on` edges[^plugin-hook].
2. **Wheel & Editable Artifact Mapping**: Maps `python-extension` modules directly to dotted package destinations (`pkg._core` &rarr; `pkg/_core.so`), maps standalone native outputs via explicit `install = { kind, path }` rules, sets `infer_tag = True` and `pure_python = False` for native wheels, and supports editable-install copy-back into `""`, `"src"`, or `"src/py"` package trees[^plugin-hook].
3. **Self-Contained Runtime Bundling**: Walks `ldd` (Linux) or `otool -L` (macOS) graphs starting from compiled extension artifacts to bundle required `modular/lib` shared libraries, patch `$ORIGIN` / `@loader_path` RPATHs, ad-hoc re-sign Mach-O outputs, and emit `NOTICE.mojo-runtime`[^runtime-bundler].

## Provenance

[^pyproject-entry]: `pyproject.toml` — Declares `[project.entry-points.hatch] mojo = "hatch_mojo.hooks"` and runtime dependencies `hatchling>=1.26.0`, `packaging>=24.0`.
[^hook-entry]: `hatch_mojo/hooks.py::hatch_register_build_hook` — Exposes `MojoBuildHook` to Hatchling's plugin manager.
[^plugin-hook]: `hatch_mojo/plugin.py::MojoBuildHook` — Orchestrates config parsing, job planning, compilation, runtime bundling, artifact registration, editable copy-back, and manifest cleanup.
[^runtime-bundler]: `hatch_mojo/runtime.py::bundle_runtime_libs` — Bundles Modular SDK runtime libraries into `<pkg>.libs/` and rewrites dynamic linker paths on Linux and macOS.
