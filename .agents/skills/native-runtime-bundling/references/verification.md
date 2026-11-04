# Cross-Platform Runtime Bundling Verification (`native-runtime-bundling`)

## Testing Strategy (`tests/test_runtime.py`)

CI runs across `ubuntu-latest`, `macos-latest`, and `windows-latest` without requiring a preinstalled Modular SDK. `tests/test_runtime.py` exercises real filesystem staging in `tmp_path` while patching only the OS/process boundary:

1. **Real Staging & File Permissions**: Create fake `modular/lib` directories (`_make_modular_lib`) with real read-only or writable byte files so `shutil.copy2`, `chmod(S_IWUSR)`, `NOTICE.mojo-runtime` (`Apache-2.0 WITH LLVM-exception` vs MAX supplement), and `LICENSE.mojo-runtime` run against real files on disk.
2. **Simulated `sys.platform` Contexts**: Patch `sys.platform` (`"linux"`, `"darwin"`, `"win32"`) *inside* the `with` block prior to calling `_sentinel()` or `_make_modular_lib` when testing `.dylib` vs `.so` naming, `mojo-compiler` / wrapper-venv discovery, and `_is_ephemeral_sdk`.
3. **Subprocess Call Order & Idempotency Assertions**:
   - Verify exact `install_name_tool` &rarr; `codesign` ordering (`codesign` must always run *last* after all load-command mutations across `_patch_macos_dylibs`, `_patch_macos_extension`, `_patch_rpath`, and `patch_editable_runtime`).
   - Verify `_strip_absolute_rpaths` ignores `LC_LOAD_DYLIB` entries while stripping non-`@` `LC_RPATH` entries.
   - Verify `subprocess.CalledProcessError` with `stderr="already contains LC_RPATH"` or `"no LC_RPATH found"` succeeds silently on idempotent paths, whereas unrelated `stderr` raises `RuntimeError` containing the `stderr` payload.
   - Verify cyclic dependency graphs (`libA -> libB -> libA`) and `ldd` `=> not found` sibling entries terminate cleanly in `_resolve_modular_dependencies`.

## Verification Commands

```bash
# Focused runtime bundling test suite
uv run pytest tests/test_runtime.py -q

# Reproduce a single Mach-O, ELF, or editable bundling case
uv run pytest tests/test_runtime.py -k "macos or editable" -vv

# Full static + slotscheck gate
uv run ruff check . && uv run ruff format --check . && uv run mypy && uv run pyright && uv run slotscheck hatch_mojo
```
