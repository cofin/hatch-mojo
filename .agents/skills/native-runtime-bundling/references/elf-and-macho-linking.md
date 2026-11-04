# ELF and Mach-O Linking Contract (`native-runtime-bundling`)

## 1. SDK Discovery & Dynamic Graph Walk (`hatch_mojo/runtime.py`)

- **Sentinel Verification**: `_sentinel()` returns `libKGENCompilerRTShared.dylib` on `darwin` and `libKGENCompilerRTShared.so` on Linux. Every candidate path in `discover_modular_lib` must contain this file before returning.
- **Compiler-Matched Discovery Order**:
  1. `MODULAR_LIB_DIR` environment variable
  2. Ancestor `lib/` walk from `shutil.which`-resolved `mojo_bin` plus wrapper-venv `lib/python*/site-packages/{modular,mojo,max}/lib`
  3. `mojo._package_root.get_package_root()` (`mojo-compiler` / `mojo` PyPI wheels)
  4. `importlib.util.find_spec` across `("mojo", "mojo_compiler", "max", "modular")`
  5. Conda/Pixi/venv prefixes (`CONDA_PREFIX`, `PIXI_ENVIRONMENT_PATH`, `VIRTUAL_ENV`, `sys.prefix`, `<root>/.pixi/envs/default`, `<root>/.venv`)
  6. Legacy `/opt/modular/lib` and `<root>/.modular/lib`
- **Inspector Dispatch (`_get_linked_libraries`)**:
  - `darwin`: Runs `["otool", "-L", str(target)]`, skips line `0`, and extracts load paths.
  - Linux: Runs `["ldd", str(target)]`, extracting resolved `=> <path>` entries, direct `/...` loader entries, and `=> not found` basenames (`_LDD_NOT_FOUND_RE`) so uninstalled SDK siblings inside `modular_lib` still resolve during BFS.

## 2. Wheel & Editable RPATH Layouts

- **`platlib` targets** (`python-extension`, `package`, `root`, `force-include`): stage libraries at `<root>/<build_dir>/<pkg_name>.libs/` (`force_include` &rarr; `<pkg_name>.libs/<lib>`) and compute RPATH via `_compute_relative_rpath(posixpath.dirname(install_target) or ".", f"{pkg_name}.libs")`:
  - `_core.so` (`depth = 0`) &rarr; `[origin, f"{origin}/pkg.libs"]`
  - `mogemma/_core.so` (`depth = 1`) &rarr; `[origin, f"{origin}/../mogemma.libs"]`
  - `pkg/sub/_core.so` (`depth = 2`) &rarr; `[origin, f"{origin}/../../pkg.libs"]`
- **`.data/` targets** (`scripts`, `data`): stage libraries at `<root>/<build_dir>/data/<dist>.libs/` (`shared_data` &rarr; `lib/<dist>.libs/<lib>`) and compute RPATH from `scripts/<dir>` or `<data_dir>` to `lib/<dist>.libs` (e.g. `[origin, f"{origin}/../lib/<dist>.libs"]`).
- **Editable targets (`patch_editable_runtime`)**: patch editable destination copies directly to `[str(modular_lib.resolve())]` when persistent, or stage relocated libraries + `NOTICE.mojo-runtime` into `<root>/<build_dir>/editable.libs/` when `_is_ephemeral_sdk(modular_lib, root)` detects an external tempdir, `builds-v0`, `.tmp*`, or `pip-build-env-*` path.

## 3. Platform Patching Sequences

### Linux (ELF)

1. Copy resolved `.so` files and ensure `stat.S_IWUSR` (`chmod`).
2. Patch every staged `.so` via `patchelf --set-rpath $ORIGIN <lib>`.
3. Patch each compiled `python-extension`, `shared-lib`, or `executable` binary via `patchelf --set-rpath <joined_rpaths> <target>`.

### macOS (Mach-O)

1. Compile with `-Xlinker -headerpad_max_install_names` (`hatch_mojo/compiler.py::build_command`).
2. Copy resolved `.dylib` files and ensure `stat.S_IWUSR` (`chmod`).
3. For each staged `.dylib` (`_patch_macos_dylibs`):
   - `_strip_absolute_rpaths(target)`: track `cmd LC_RPATH` blocks in `otool -l` output and delete any `path` not starting with `@`.
   - `_run_install_name_tool(["-id", f"@rpath/{filename}", str(target)])`.
   - Rewrite sibling references via `-change <ref> @rpath/<basename>` and call `_resign_ad_hoc(target)`.
4. For each compiled Mach-O target (`_patch_macos_extension`):
   - Call `_strip_absolute_rpaths(target)` to remove build-host SDK RPATHs.
   - If `is_shared_lib`, set `-id @rpath/<target.name>`.
   - Rewrite linked Modular dylib references to `@rpath/<basename>`, add relative RPATHs via `-add_rpath`, and call `_resign_ad_hoc(target)`.

## 4. Redistribution Notice Invariant (`_write_license_notice`)

- Always generate `NOTICE.mojo-runtime` under `Apache-2.0 WITH LLVM-exception` (`Copyright (c) Modular Inc, a Qualcomm Company`), appending the MAX Community License Section 1.5 supplement only when `_is_max_only_library` matches bundled libraries (`libMAX*`, `libMogg*`, etc.).
- Copy `modular_lib.parent / "LICENSE"` to `LICENSE.mojo-runtime` when present as a regular file.
