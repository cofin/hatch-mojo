---
type: Decision
title: "ADR-002: Idempotent Mach-O RPATH Patching and Ad-Hoc Signing"
description: Patch Mach-O dylibs and extensions directly via _run_install_name_tool error-substring idempotency plus ad-hoc codesign.
status: stable
tags: [decision, macos, mach-o]
generated:
  by: flow/0.26.0
  at: 2026-11-04T03:56:00Z
verified:
  - by: agent:flow-setup
    at: 2026-11-04T03:56:00Z
    commit: 1b6d139
sources:
  - id: int-wrapper
    resource: hatch_mojo/runtime.py::_run_install_name_tool
    title: Subprocess wrapper handling stderr reporting and idempotent error substrings
  - id: patch-dylibs
    resource: hatch_mojo/runtime.py::_patch_macos_dylibs
    title: Dylib absolute RPATH stripping, LC_ID_DYLIB rewrite, sibling -change, and ad-hoc signing
  - id: compiler-pad
    resource: hatch_mojo/compiler.py::build_command
    title: Compile-time -headerpad_max_install_names linker flag on Darwin
---

# ADR-002: Idempotent Mach-O RPATH Patching and Ad-Hoc Signing

<!-- truth: start -->
- Patch macOS wheels inside `hatch-mojo` during hook execution (`-headerpad_max_install_names` &rarr; `_strip_absolute_rpaths` &rarr; `-id @rpath/<lib>` &rarr; `-change` sibling refs &rarr; `-add_rpath @loader_path/...` &rarr; `codesign -s - -f`)[^int-wrapper][^patch-dylibs][^compiler-pad].
- Rely on `install_name_tool` `stderr` substrings (`already contains LC_RPATH`, `no LC_RPATH found`) for idempotency rather than `otool -l` pre-check regexes[^int-wrapper].
<!-- truth: end -->

## Context

macOS Mojo binaries embed absolute SDK paths (e.g., `/opt/modular/lib/libKGENCompilerRTShared.dylib`) and residual SDK `LC_RPATH` load commands. Additionally, macOS System Integrity Protection (SIP) strips `DYLD_LIBRARY_PATH` from subshells in `cibuildwheel`, preventing `delocate-wheel` from finding unbundled SDK libraries unless wheels are already self-consistent via `@rpath` and `@loader_path`. Earlier `otool -l` regex pre-checks failed when RPATH formatting varied and swallowed `install_name_tool` `stderr` on failure.

## Decision

1. Inject `-Xlinker -headerpad_max_install_names` during `mojo build` on Darwin so load commands have room to grow[^compiler-pad].
2. Strip non-`@` `LC_RPATH` entries from copied dylibs, rewrite each dylib's `LC_ID_DYLIB` and sibling references to `@rpath/<basename>`, rewrite extension references, add `@loader_path` and `@loader_path/<up>/<pkg>.libs` RPATHs, and ad-hoc re-sign every modified Mach-O file with `codesign -s - -f`[^patch-dylibs].
3. Execute all `install_name_tool` operations through `_run_install_name_tool` using `ignore_errors` substrings for idempotent re-runs and raising `RuntimeError` with full `stderr` on genuine errors[^int-wrapper].

## Consequences & Trade-Offs

- **Gain**: Produces wheels that work directly on developer machines (without `delocate` or `DYLD_LIBRARY_PATH`) and pass `delocate-wheel` cleanly in `cibuildwheel` under macOS SIP, with clear diagnostics when Mach-O patching fails.
- **Cost**: Requires Xcode Command Line Tools (`otool`, `install_name_tool`, `codesign`) on macOS build hosts and couples idempotency to Apple's stable `install_name_tool` diagnostic substrings.

## Rejected Alternatives

- **Delegating all Mach-O rewriting to `delocate-wheel`**: Rejected because SIP strips `DYLD_LIBRARY_PATH` in `cibuildwheel` repair subshells and local `uv build` / `hatch build` runs do not invoke `delocate`.
- **Pre-checking RPATH existence with `otool -l` regexes**: Rejected after fragile regex mismatches caused `install_name_tool -add_rpath` crashes on valid binaries.

## Provenance

[^int-wrapper]: `hatch_mojo/runtime.py::_run_install_name_tool` — Centralizes `install_name_tool` execution, idempotency substrings, and `stderr` propagation.
[^patch-dylibs]: `hatch_mojo/runtime.py::_patch_macos_dylibs` — Rewrites dylib install names, sibling references, and ad-hoc signatures.
[^compiler-pad]: `hatch_mojo/compiler.py::build_command` — Passes `-Xlinker -headerpad_max_install_names` to `mojo build` on Darwin.
