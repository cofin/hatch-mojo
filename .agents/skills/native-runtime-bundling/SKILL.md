---
name: native-runtime-bundling
description: "Use when modifying Modular SDK runtime library discovery, recursive ldd or otool -L dependency resolution, Linux ELF patchelf RPATH rewriting, macOS Mach-O install_name_tool patching and ad-hoc codesign, or NOTICE.mojo-runtime bundling in hatch_mojo/runtime.py and tests/test_runtime.py."
---

# Native Runtime Bundling (`native-runtime-bundling`)

<!-- truth: start -->
- Discover `modular/lib` via `discover_modular_lib` in strict compiler-matched priority order (`MODULAR_LIB_DIR` &rarr; ancestor walk from resolved `mojo_bin` + external tool-venv `site-packages/{modular,mojo,max}/lib` &rarr; `mojo._package_root` &rarr; `importlib.util.find_spec` across `("mojo", "mojo_compiler", "max", "modular")` &rarr; Conda/Pixi/venv prefixes &rarr; `/opt/modular/lib` and `<root>/.modular/lib`), verifying every candidate contains `_sentinel()` (`libKGENCompilerRTShared.{so,dylib}`).
- Resolve bundled libraries dynamically via `_resolve_modular_dependencies` (`ldd` on Linux including `not found` basenames, `otool -L` on macOS), filtering by membership in `modular/lib` and force-seeding `_sentinel()` across `python-extension`, `shared-lib`, and `executable` jobs; never reintroduce static library filename lists.
- Stage `platlib` runtime libraries in `<build_dir>/<pkg_name>.libs/` (`force_include`) and `.data/` (`scripts`/`data`) runtime libraries in `<build_dir>/data/<dist>.libs/` (`shared_data` `lib/<dist>.libs/`) with `stat.S_IWUSR`, returning `RuntimeBundleResult` and writing `NOTICE.mojo-runtime` under `Apache-2.0 WITH LLVM-exception` (appending MAX license terms only when MAX libraries are bundled).
- Route every `install_name_tool` call through `_run_install_name_tool` with `capture_output=True, text=True`, explicit `ignore_errors` substrings (`already contains LC_RPATH`, `no LC_RPATH found`), `cmd LC_RPATH`-scoped `_strip_absolute_rpaths`, `-id @rpath/<name>` on `shared-lib` targets, and `_resign_ad_hoc` (`codesign -s - -f`) across `_patch_macos_dylibs`, `_patch_macos_extension`, `_patch_rpath`, and `patch_editable_runtime`.
- Short-circuit `bundle_runtime_libs` (`RuntimeBundleResult({}, {}, ())`), `patch_editable_runtime` (`()`), and `_patch_rpath` cleanly on `sys.platform == "win32"`.
<!-- truth: end -->

## Scope

Covers `hatch_mojo/runtime.py`, `RuntimeBundleResult` in `hatch_mojo/types.py`, Darwin linker preparation in `hatch_mojo/compiler.py::build_command`, and cross-platform binary-relocation tests in `tests/test_runtime.py` and `tests/test_integration_wheel.py`.

## Workflow

1. **Inspect Linking & Relocation Rules**:
   - Load [`references/elf-and-macho-linking.md`](references/elf-and-macho-linking.md) before modifying `discover_modular_lib`, `_get_linked_libraries`, `_resolve_modular_dependencies`, `_compute_relative_rpath`, `patch_editable_runtime`, ELF `patchelf`, or Mach-O `install_name_tool` / `codesign` sequences.
2. **Preserve Self-Contained Wheel & Editable Invariants**:
   - Separate `platlib` jobs (`force_include` `<pkg>.libs/`) from `.data/` jobs (`shared_data` `lib/<dist>.libs/`) and compute relative RPATHs via `posixpath.relpath` (`_compute_relative_rpath`) so depth-0 (`_core.so` &rarr; `$ORIGIN/pkg.libs`) and `.data/scripts/` (`$ORIGIN/../lib/<dist>.libs`) resolve cleanly.
   - For editable installs (`patch_editable_runtime`), patch persistent SDK `modular_lib` paths directly without copying `.so`/`.dylib` files, and stage `<build_dir>/editable.libs` only when `_is_ephemeral_sdk(modular_lib, root)` detects a temporary PEP 517 build environment.
   - Surface captured `stderr` in `RuntimeError` whenever `ldd`, `otool`, or `install_name_tool` fails with an unignored error.
3. **Verify Across Simulated & Real OS Targets**:
   - Load [`references/verification.md`](references/verification.md) to exercise Linux (`linux`), macOS (`darwin`), and Windows (`win32`) branches in `tests/test_runtime.py`.

## Guardrails

- Never mutate a Mach-O dylib, extension, executable, or editable copy with `install_name_tool` without calling `_resign_ad_hoc(target)` afterward; unsigned mutations crash at load time on Apple Silicon (`EXC_BAD_ACCESS` / `SIGKILL`).
- Never rewrite macOS system library references (`/usr/lib/*`, `/System/*`) or already-relative references (`@rpath/*`, `@loader_path/*`).
- Never match `LC_LOAD_DYLIB` paths in `_strip_absolute_rpaths`; track `cmd LC_RPATH` blocks strictly in `otool -l` output and strip residual absolute RPATHs on both bundled dylibs and compiled Mach-O outputs.

## Validation

```bash
uv run ruff check . && uv run ruff format --check . && uv run mypy && uv run pyright && uv run slotscheck hatch_mojo
uv run pytest tests/test_runtime.py tests/test_integration_wheel.py -q
```

## References

- [ELF and Mach-O Linking Contract](references/elf-and-macho-linking.md)
- [Cross-Platform Runtime Bundling Verification](references/verification.md)
