# False-Positive Suppressions (`FP-NRB-01..FP-NRB-05`)

Reviewers **MUST NOT** flag the intentional repository patterns below:

- **`FP-NRB-01` — DO NOT FLAG `# noqa: S607` on `otool`, `ldd`, `install_name_tool`, `codesign`, or `patchelf` calls**:
  Resolving standard OS toolchain binaries from `PATH` via argument lists (`shell=False`) is required across diverse Linux/macOS build environments where binary locations vary (`/usr/bin` vs Nix/Homebrew/conda).
- **`FP-NRB-02` — DO NOT FLAG Windows (`sys.platform == "win32"`) returning `RuntimeBundleResult({}, {}, ())` in `bundle_runtime_libs`, `()` in `patch_editable_runtime`, and no-oping in `_patch_rpath`**:
  Mojo runtime wheel bundling targets Linux ELF and macOS Mach-O; Windows PE/DLL packaging has no RPATH concept and intentionally short-circuits cleanly.
- **`FP-NRB-03` — DO NOT FLAG force-seeding `_sentinel()` (`libKGENCompilerRTShared`) in `bundle_runtime_libs` and `patch_editable_runtime`**:
  Even if `ldd`/`otool -L` on a minimal target does not list `libKGENCompilerRTShared` directly, the Mojo runtime expects the root runtime library and its transitive dependencies inside `<pkg>.libs/` or `lib/<dist>.libs/`.
- **`FP-NRB-04` — DO NOT FLAG ad-hoc `codesign -s - -f` identity (`"-"`)**:
  Wheel build hooks cannot access Apple Developer signing certificates during third-party builds; ad-hoc signing (`-s -`) is the standard macOS mechanism required by `delocate` and the ARM64 kernel loader after `install_name_tool` header edits.
- **`FP-NRB-05` — DO NOT FLAG mocking `subprocess.run` and `sys.platform` in `tests/test_runtime.py`**:
  `otool`, `install_name_tool`, `codesign`, `patchelf`, and the Modular SDK are external boundary dependencies not preinstalled across every OS in the `ubuntu-latest` / `macos-latest` / `windows-latest` CI matrix; mocking `subprocess.run` while testing real `tmp_path` files is the required boundary test strategy.
