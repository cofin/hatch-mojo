---
name: native-runtime-bundling
description: "Use when modifying Modular SDK runtime library discovery, recursive ldd or otool -L dependency resolution, Linux ELF patchelf RPATH rewriting, macOS Mach-O install_name_tool patching and ad-hoc codesign, or NOTICE.mojo-runtime bundling in hatch_mojo/runtime.py and tests/test_runtime.py."
---

# Native Runtime Bundling (`native-runtime-bundling`)

<!-- truth: start -->
- Discover `modular/lib` via `discover_modular_lib` in strict priority order (`MODULAR_LIB_DIR` &rarr; `importlib.util.find_spec("modular")` &rarr; ancestor walk from `mojo_bin` &rarr; `/opt/modular/lib` and `<root>/.modular/lib`), verifying every candidate contains `_sentinel()` (`libKGENCompilerRTShared.{so,dylib}`).
- Resolve bundled libraries dynamically via `_resolve_modular_dependencies` (`ldd` on Linux, `otool -L` on macOS), filtering by membership in `modular/lib` and force-seeding `_sentinel()` when present; never reintroduce static library filename lists.
- Ensure copied runtime libraries in `<build_dir>/<pkg_name>.libs/` have owner write permission (`stat.S_IWUSR`) before running `patchelf` or `install_name_tool`, and always include `NOTICE.mojo-runtime` (plus `LICENSE.mojo-runtime` if `modular/LICENSE` exists).
- Route every `install_name_tool` call through `_run_install_name_tool` with `capture_output=True, text=True`, explicit `ignore_errors` substrings (`already contains LC_RPATH`, `no LC_RPATH found`), `_strip_absolute_rpaths`, and `_resign_ad_hoc` (`codesign -s - -f`).
- Short-circuit `bundle_runtime_libs` and `_patch_rpath` cleanly to no-ops on `sys.platform == "win32"`.
<!-- truth: end -->

## Scope

Covers `hatch_mojo/runtime.py`, Darwin linker preparation in `hatch_mojo/compiler.py::build_command`, and cross-platform binary-relocation tests in `tests/test_runtime.py` and `tests/test_integration_wheel.py`.

## Workflow

1. **Inspect Linking & Relocation Rules**:
   - Load [`references/elf-and-macho-linking.md`](references/elf-and-macho-linking.md) before modifying `discover_modular_lib`, `_get_linked_libraries`, `_resolve_modular_dependencies`, RPATH depth formulas, ELF `patchelf`, or Mach-O `install_name_tool` / `codesign` sequences.
2. **Preserve Self-Contained Wheel Invariants**:
   - Group `python-extension` jobs by top-level package (`job.module.split(".")[0]`), stage libraries per package in `<build_dir>/<pkg>.libs/`, and compute extension RPATHs from dotted module depth (`len(module.split(".")) - 1`).
   - Surface captured `stderr` in `RuntimeError` whenever `ldd`, `otool`, or `install_name_tool` fails with an unignored error.
3. **Verify Across Simulated OS Targets**:
   - Load [`references/verification.md`](references/verification.md) to exercise Linux (`linux`), macOS (`darwin`), and Windows (`win32`) branches in `tests/test_runtime.py` without requiring local Modular SDK or macOS toolchains.

## Guardrails

- Never mutate a Mach-O dylib or extension with `install_name_tool` without calling `_resign_ad_hoc(target)` afterward; unsigned mutations crash at load time on Apple Silicon (`EXC_BAD_ACCESS` / `SIGKILL`).
- Never rewrite macOS system library references (`/usr/lib/*`, `/System/*`) or already-relative references (`@rpath/*`, `@loader_path/*`).
- Never leave residual non-`@` `LC_RPATH` entries inside bundled macOS dylibs (`_strip_absolute_rpaths`).

## Validation

```bash
uv run ruff check . && uv run ruff format --check . && uv run mypy && uv run pyright && uv run slotscheck hatch_mojo
uv run pytest tests/test_runtime.py tests/test_integration_wheel.py -q
```

## References

- [ELF and Mach-O Linking Contract](references/elf-and-macho-linking.md)
- [Cross-Platform Runtime Bundling Verification](references/verification.md)
