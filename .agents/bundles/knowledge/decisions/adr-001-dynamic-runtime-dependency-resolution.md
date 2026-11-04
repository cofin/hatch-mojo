---
type: Decision
title: "ADR-001: Dynamic Runtime Dependency Resolution"
description: Resolve Modular runtime libraries dynamically via recursive ldd and otool -L walking bounded by modular/lib and libKGENCompilerRTShared.
status: stable
tags: [decision, runtime, bundling]
generated:
  by: flow/0.26.0
  at: 2026-11-04T03:56:00Z
verified:
  - by: agent:flow-setup
    at: 2026-11-04T03:56:00Z
    commit: 1b6d139
sources:
  - id: resolve-deps
    resource: hatch_mojo/runtime.py::_resolve_modular_dependencies
    title: Breadth-first transitive dependency walk restricted to modular/lib
  - id: linked-libs
    resource: hatch_mojo/runtime.py::_get_linked_libraries
    title: Platform-dispatched otool -L and ldd output parser
  - id: bundle-sentinel
    resource: hatch_mojo/runtime.py::bundle_runtime_libs
    title: Sentinel library inclusion and per-package .libs staging
---

# ADR-001: Dynamic Runtime Dependency Resolution

<!-- truth: start -->
- Discover required Mojo runtime libraries per top-level Python package by walking `ldd` (Linux) or `otool -L` (macOS) transitive links from each compiled extension output and retaining only basenames present inside `modular/lib`[^resolve-deps][^linked-libs].
- Always include the `libKGENCompilerRTShared` sentinel (and its transitive `modular/lib` dependencies) if present in `modular/lib`, even when not directly listed in initial extension headers[^bundle-sentinel].
- Never reintroduce hardcoded Modular library filename tuples (`_RUNTIME_LIB_BASES`).
<!-- truth: end -->

## Context

Early versions of `hatch-mojo` hardcoded a static list of Modular SDK shared library names. Across Mojo releases and OS targets, the SDK split, renamed, or omitted platform-specific libraries (such as CUDA/NVPTX libraries absent on macOS), breaking wheel builds whenever the SDK changed.

## Decision

1. Parse direct shared-library dependencies of each built `python-extension` binary via `otool -L` on macOS and `ldd` on Linux (`_get_linked_libraries`), raising `RuntimeError` immediately if the inspector tool fails[^linked-libs].
2. Perform a breadth-first walk (`_resolve_modular_dependencies`) keeping only libraries whose basename exists inside the discovered `modular/lib` directory, automatically excluding OS system libraries (`/usr/lib`, `libc`, `libm`, `linux-vdso`)[^resolve-deps].
3. Guarantee inclusion of `_sentinel()` (`libKGENCompilerRTShared.{so,dylib}`) and its transitive `modular/lib` dependencies, staging the union under `<build_dir>/<pkg_name>.libs/`[^bundle-sentinel].

## Consequences & Trade-Offs

- **Gain**: Survives Modular SDK library additions, splits, and OS-specific omissions without `hatch-mojo` code releases, and bundles only libraries actually linked by the package's extensions plus the runtime root.
- **Cost**: Requires `ldd` (Linux) or `otool` (macOS) on the build host, and misses libraries loaded exclusively via `dlopen` at runtime unless reachable from `libKGENCompilerRTShared` (the explicit reason the sentinel is force-seeded)[^bundle-sentinel].

## Rejected Alternatives

- **Hardcoded per-OS allowlists**: Rejected because Modular SDK internal library names change across minor versions.
- **Copying every file inside `modular/lib/`**: Rejected because `modular/lib` contains compiler/LLVM/MAX artifacts totaling hundreds of megabytes unrelated to Python extension execution.

## Provenance

[^resolve-deps]: `hatch_mojo/runtime.py::_resolve_modular_dependencies` — BFS graph walk filtered by `modular_lib` membership.
[^linked-libs]: `hatch_mojo/runtime.py::_get_linked_libraries` — Parses `otool -L` and `ldd` stdout and raises `RuntimeError` on tool failure.
[^bundle-sentinel]: `hatch_mojo/runtime.py::bundle_runtime_libs` — Seeds `_sentinel()` and stages `<pkg_name>.libs/` entries.
