---
type: Guide
title: Platform Linking and Build Quirks
description: macOS Mach-O header space, ARM64 ad-hoc code signing, residual SDK RPATHs, read-only lib permissions, Windows script invocation, and _default_output path behavior.
status: stable
tags: [gotchas, macos, linux, windows]
generated:
  by: flow/0.26.0
  at: 2026-11-04T03:56:00Z
verified:
  - by: agent:flow-setup
    at: 2026-11-04T03:56:00Z
    commit: 1b6d139
sources:
  - id: darwin-headerpad
    resource: hatch_mojo/compiler.py::build_command
    title: Darwin -Xlinker -headerpad_max_install_names injection
  - id: darwin-codesign
    resource: hatch_mojo/runtime.py::_resign_ad_hoc
    title: Ad-hoc codesign after Mach-O install_name_tool mutation
  - id: darwin-strip-rpath
    resource: hatch_mojo/runtime.py::_strip_absolute_rpaths
    title: Removal of residual absolute SDK RPATHs from bundled dylibs
  - id: chmod-writable
    resource: hatch_mojo/runtime.py::bundle_runtime_libs
    title: Adding S_IWUSR write permission on copied SDK runtime libraries
  - id: win32-compiler
    resource: hatch_mojo/compiler.py::compile_job
    title: Windows .exe resolution and sys.executable wrapper for script stubs
  - id: planner-default-out
    resource: hatch_mojo/planner.py::_default_output
    title: Default output path construction in planner
---

# Platform Linking and Build Quirks

<!-- truth: start -->
- On `darwin`, `build_command` must pass `-Xlinker -headerpad_max_install_names` for `python-extension`, `shared-lib`, and `executable` emits so `install_name_tool` has sufficient Mach-O header space to rewrite load commands later[^darwin-headerpad].
- On `darwin` (especially `arm64`), every `install_name_tool` mutation invalidates the Mach-O signature and causes the OS loader to kill the process (`EXC_BAD_ACCESS` / `SIGKILL`); always call `_resign_ad_hoc` (`codesign -s - -f`) after patching dylibs or extensions[^darwin-codesign].
- Bundled Modular dylibs carry residual absolute RPATHs (such as `/opt/modular/lib`) from the SDK build environment; always call `_strip_absolute_rpaths` so developer machines do not load mismatched local SDK dylibs ahead of `<pkg>.libs/`[^darwin-strip-rpath].
- Modular SDK libraries in read-only virtualenvs/containers lack owner write bits (`0o444`); always apply `stat.S_IWUSR` (`chmod`) after `shutil.copy2` before running `patchelf` or `install_name_tool`[^chmod-writable].
- On `win32`, `bundle_runtime_libs` and `_patch_rpath` intentionally no-op, while `compile_job` appends `.exe` if present or prefixes `sys.executable` when invoking script-based test stubs[^win32-compiler].
<!-- truth: end -->

## Detailed Footguns

### 1. macOS SIP Strips `DYLD_LIBRARY_PATH` in Child Shells

macOS System Integrity Protection strips `DYLD_LIBRARY_PATH` across `/bin/sh` child invocations (including `cibuildwheel` `CIBW_ENVIRONMENT`). Wheel bundling via `@rpath` + `@loader_path/../<pkg>.libs` avoids relying on `DYLD_LIBRARY_PATH` during `delocate-wheel`.

### 2. Linux `manylinux_2_34+` Baseline & `auditwheel`

The Modular SDK links against newer `GLIBCXX` symbols requiring `manylinux_2_34` or newer. When `bundle-libs = true` already stages Modular libs and sets `$ORIGIN` RPATHs via `patchelf`, `auditwheel repair` may reject the wheel or duplicate mangled names; retagging with `python -m wheel tags` is preferred for `cibuildwheel` Linux builds.

### 3. `planner._default_output` Hardcodes `"build/mojo"`

In `hatch_mojo/planner.py::_default_output`[^planner-default-out], default output paths resolve to `root / "build/mojo" / ...` rather than reading `config.build_dir` (whereas `bundle_runtime_libs`, `save_manifest`, and `clean_from_manifest` read `config.build_dir`). Keep this behavior in mind whenever touching custom `build-dir` handling or refactoring `planner.py`.

### 4. Editable Copy-Back Requires Package Marker File

`hatch_mojo/plugin.py::_copy_editable_artifacts` checks `("", "src", "src/py")` in order and only copies into a candidate `<layout>/<pkg_name>` directory if `__init__.py` or `__init__.mojo` exists inside it. Namespace packages without either marker file are skipped silently.

## Provenance

[^darwin-headerpad]: `hatch_mojo/compiler.py::build_command` — Appends `-Xlinker -headerpad_max_install_names` on macOS linkable targets.
[^darwin-codesign]: `hatch_mojo/runtime.py::_resign_ad_hoc` — Runs `codesign -s - -f` to restore valid ad-hoc Mach-O signatures.
[^darwin-strip-rpath]: `hatch_mojo/runtime.py::_strip_absolute_rpaths` — Strips non-`@`-prefixed `LC_RPATH` entries from copied SDK dylibs.
[^chmod-writable]: `hatch_mojo/runtime.py::bundle_runtime_libs` — Sets `stat.S_IWUSR` on copied runtime libraries prior to RPATH patching.
[^win32-compiler]: `hatch_mojo/compiler.py::compile_job` — Resolves `.exe` binaries and wraps script executables with `sys.executable` on Windows.
[^planner-default-out]: `hatch_mojo/planner.py::_default_output` — Computes default output paths under `root / "build/mojo"`.
