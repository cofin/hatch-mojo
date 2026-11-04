# ELF and Mach-O Linking Contract (`native-runtime-bundling`)

## 1. SDK Discovery & Dynamic Graph Walk (`hatch_mojo/runtime.py`)

- **Sentinel Verification**: `_sentinel()` returns `libKGENCompilerRTShared.dylib` on `darwin` and `libKGENCompilerRTShared.so` on Linux. Every candidate path in `discover_modular_lib` must contain this file before returning, including namespace-package `spec.submodule_search_locations`.
- **Inspector Dispatch (`_get_linked_libraries`)**:
  - `darwin`: Runs `["otool", "-L", str(target)]`, skips line `0` (the binary header), and extracts paths matching `^\s+(.+?)\s+\(compatibility version`.
  - Linux: Runs `["ldd", str(target)]`, extracting resolved paths from `=> <path> (0x...)` (`_LDD_LIB_RE`) and direct absolute loader entries `/... (0x...)` (`_LDD_LIB_ABS_RE`), ignoring virtual `linux-vdso.so.1`.
  - Any `CalledProcessError` raises `RuntimeError` containing the tool name and `e.stderr`.
- **Transitive Closure (`_resolve_modular_dependencies`)**: Breadth-first search starting from `job.output_path`. Only basenames that exist inside `modular_lib` are added to `seen` and enqueued, naturally excluding OS libraries while handling cyclic sibling links (`libA` &harr; `libB`).

## 2. Wheel Layout & RPATH Depth Formula

- Bundled libraries stage at `<root>/<build_dir>/<pkg_name>.libs/<filename>` and map in Hatch `force_include` to `<pkg_name>.libs/<filename>`.
- `_compute_extension_rpath(module, pkg_name)` uses `origin = "@loader_path"` (`darwin`) or `"$ORIGIN"` (Linux) and `depth = len(module.split(".")) - 1`:
  - `mogemma._core` (`depth = 1`) &rarr; `[origin, f"{origin}/../mogemma.libs"]`
  - `pkg.sub._core` (`depth = 2`) &rarr; `[origin, f"{origin}/../../pkg.libs"]`

## 3. Platform Patching Sequences

### Linux (ELF)

1. Copy resolved `.so` files and ensure `stat.S_IWUSR` (`chmod`).
2. Patch every bundled `.so` in `<pkg>.libs/` via `patchelf --set-rpath $ORIGIN <lib>`.
3. Patch each compiled extension `.so` via `patchelf --set-rpath $ORIGIN:$ORIGIN/<up>/<pkg>.libs <ext>`.

### macOS (Mach-O)

1. Compile with `-Xlinker -headerpad_max_install_names` (`hatch_mojo/compiler.py::build_command`).
2. Copy resolved `.dylib` files and ensure `stat.S_IWUSR` (`chmod`).
3. For each bundled `.dylib` (`_patch_macos_dylibs`):
   - `_strip_absolute_rpaths(target)`: parse `otool -l` `path ` lines and delete any RPATH not starting with `@` (`ignore_errors=["no LC_RPATH found"]`).
   - `_run_install_name_tool(["-id", f"@rpath/{filename}", str(target)])`.
   - Rewrite sibling references in `_get_linked_libraries(target)` whose basename is in `lib_filenames` (skipping `@rpath/`, `@loader_path/`, `/usr/lib/`, `/System/`) via `-change <ref> @rpath/<basename>`.
   - `_resign_ad_hoc(target)` (`codesign -s - -f`).
4. For each compiled extension (`_patch_macos_extension`):
   - Rewrite linked Modular dylib references to `@rpath/<basename>`.
   - Add `@loader_path` and `@loader_path/<up>/<pkg>.libs` via `-add_rpath` (`ignore_errors=["already contains LC_RPATH"]`).
   - `_resign_ad_hoc(ext)`.

## 4. Redistribution Notice Invariant (`_write_license_notice`)

- Always generate `<pkg>.libs/NOTICE.mojo-runtime` listing sorted `lib_filenames` under the Modular Community License notice.
- Copy `modular_lib.parent / "LICENSE"` to `<pkg>.libs/LICENSE.mojo-runtime` when present as a regular file.
