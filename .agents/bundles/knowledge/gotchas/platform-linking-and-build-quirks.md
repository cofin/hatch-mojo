---
type: Guide
title: Platform Linking and Build Quirks
description: macOS Mach-O header space, ARM64 ad-hoc code signing, LC_RPATH stripping, ephemeral PEP 517 editable SDKs, cibuildwheel 4.x retagging, and Windows shebang stubs.
status: stable
tags: [gotchas, macos, linux, windows]
generated:
  by: flow/0.26.0
  at: 2026-11-04T03:56:00Z
verified:
  - by: agent:flow-execution
    at: 2026-11-04T20:36:52Z
    commit: 7a96a66
sources:
  - id: darwin-headerpad
    resource: hatch_mojo/compiler.py::build_command
    title: Darwin -Xlinker -headerpad_max_install_names injection
  - id: darwin-codesign
    resource: hatch_mojo/runtime.py::_resign_ad_hoc
    title: Ad-hoc codesign after Mach-O install_name_tool mutation
  - id: darwin-strip-rpath
    resource: hatch_mojo/runtime.py::_strip_absolute_rpaths
    title: LC_RPATH-scoped removal of residual absolute SDK RPATHs
  - id: chmod-writable
    resource: hatch_mojo/runtime.py::_stage_libs_into_dir
    title: Adding S_IWUSR write permission on copied SDK runtime libraries
  - id: win32-compiler
    resource: hatch_mojo/compiler.py::compile_job
    title: Windows shim resolution and shebang-guarded sys.executable wrapper
  - id: editable-ephemeral
    resource: hatch_mojo/runtime.py::_is_ephemeral_sdk
    title: Ephemeral PEP 517 build environment detection for editable RPATHs
---

# Platform Linking and Build Quirks

<!-- truth: start -->
- On `darwin`, `build_command` must pass `-Xlinker -headerpad_max_install_names` for `python-extension`, `shared-lib`, and `executable` emits (never `mojoc` precompile) so `install_name_tool` has sufficient Mach-O header space to rewrite load commands later[^darwin-headerpad].
- On `darwin` (especially `arm64`), every `install_name_tool` mutation invalidates the Mach-O signature and causes the OS loader to kill the process (`EXC_BAD_ACCESS` / `SIGKILL`); always call `_resign_ad_hoc` (`codesign -s - -f`) after patching dylibs, extensions, executables, or editable copies[^darwin-codesign].
- Bundled Modular dylibs and compiled Mach-O outputs carry residual absolute RPATHs from the SDK build environment; always call `cmd LC_RPATH`-scoped `_strip_absolute_rpaths` so developer machines do not load mismatched local SDK dylibs ahead of `<pkg>.libs/`[^darwin-strip-rpath].
- Modular SDK libraries in read-only virtualenvs/containers lack owner write bits (`0o444`); always apply `stat.S_IWUSR` (`chmod`) after `shutil.copy2` before running `patchelf` or `install_name_tool`[^chmod-writable].
- On `win32`, `bundle_runtime_libs`, `patch_editable_runtime`, and `_patch_rpath` intentionally no-op, while `compile_job` resolves `.exe`/`.cmd`/`.bat` shims via `_resolve_win32_mojo_bin` and prefixes `sys.executable` only when `_has_shebang` is `True`[^win32-compiler].
<!-- truth: end -->

## Detailed Footguns

### 1. macOS SIP Strips `DYLD_LIBRARY_PATH` in Child Shells

macOS System Integrity Protection strips `DYLD_LIBRARY_PATH` across `/bin/sh` child invocations (including `cibuildwheel` `CIBW_ENVIRONMENT`). Wheel bundling via `@rpath` + `@loader_path` avoids relying on `DYLD_LIBRARY_PATH` during `delocate-wheel`.

### 2. Linux `manylinux_2_34+` Baseline & `cibuildwheel 4.x`

The Mojo `1.2+` SDK requires `glibc >= 2.34` (`manylinux_2_34`). When `bundle-libs = true` already stages Mojo runtime libraries and sets `$ORIGIN` RPATHs via `patchelf`, `auditwheel repair` may reject the wheel or duplicate mangled names, and `cibuildwheel 4.x` no longer preinstalls `wheel` inside build environments—use `uvx wheel tags --remove --platform-tag manylinux_2_34_{platform} {wheel} && mv {wheel} {dest_dir}` instead.

### 3. Ephemeral PEP 517 Build Venvs in Editable Installs

When `mojo-compiler` is provided solely via `[build-system].requires` without a persistent local SDK, `pip` (`/tmp/pip-build-env-*`) and `uv` (`~/.cache/uv/builds-v0/.tmp*`) delete the isolated build venv as soon as `build_editable` finishes. `_is_ephemeral_sdk`[^editable-ephemeral] detects paths outside the project root matching `tempfile.gettempdir()`, `"builds-v0"`, `".tmp*"`, or `"pip-build-env-*"` and stages runtime libraries into `<root>/<build_dir>/editable.libs` so editable imports continue to resolve cleanly.

### 4. Pristine `.raw` Cache Restoration Before RPATH Mutation

`bundle_runtime_libs` and `patch_editable_runtime` mutate RPATH headers on staged binaries (`<build_dir>` outputs on standard wheel builds; editable copies on editable builds). `compile_job` stores untouched compiler outputs in `<build_dir>/.raw/<digest><suffix>` and restores them onto `job.output_path` on every cache hit so RPATH edits never corrupt subsequent builds.

## Provenance

[^darwin-headerpad]: `hatch_mojo/compiler.py::build_command` — Appends `-Xlinker -headerpad_max_install_names` on macOS linkable targets.
[^darwin-codesign]: `hatch_mojo/runtime.py::_resign_ad_hoc` — Runs `codesign -s - -f` to restore valid ad-hoc Mach-O signatures.
[^darwin-strip-rpath]: `hatch_mojo/runtime.py::_strip_absolute_rpaths` — Strips non-`@`-prefixed `LC_RPATH` entries while ignoring `LC_LOAD_DYLIB`.
[^chmod-writable]: `hatch_mojo/runtime.py::_stage_libs_into_dir` — Sets `stat.S_IWUSR` on copied runtime libraries prior to RPATH patching.
[^win32-compiler]: `hatch_mojo/compiler.py::compile_job` — Resolves Windows shims and wraps `#!` script stubs with `sys.executable`.
[^editable-ephemeral]: `hatch_mojo/runtime.py::_is_ephemeral_sdk` — Identifies temporary PEP 517 SDK locations requiring `<build_dir>/editable.libs` staging.
