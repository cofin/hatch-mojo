# Cross-Platform Runtime Bundling Verification (`native-runtime-bundling`)

## Testing Strategy (`tests/test_runtime.py`)

Because CI runs on Linux and Windows without the Modular SDK or macOS Xcode tools installed, `tests/test_runtime.py` exercises real filesystem staging in `tmp_path` while patching only the OS/process boundary:

1. **Real Staging & File Permissions**: Create fake `modular/lib` directories (`_make_modular_lib`) with real read-only or writable byte files so `shutil.copy2`, `chmod(S_IWUSR)`, `NOTICE.mojo-runtime`, and `LICENSE.mojo-runtime` run against real files on disk.
2. **Simulated `sys.platform` Contexts**: Patch `sys.platform` (`"linux"`, `"darwin"`, `"win32"`) *inside* the `with` block prior to calling `_sentinel()` or `_make_modular_lib` when testing `.dylib` vs. `.so` naming.
3. **Subprocess Call Order & Idempotency Assertions**:
   - Verify exact `install_name_tool` -> `codesign` ordering (`codesign` must always run *last* after all load-command mutations).
   - Verify `subprocess.CalledProcessError` with `stderr="already contains LC_RPATH"` or `"no LC_RPATH found"` succeeds silently on idempotent paths, whereas unrelated `stderr` raises `RuntimeError` containing the `stderr` payload.
   - Verify cyclic dependency graphs (`libA -> libB -> libA`) terminate cleanly in `_resolve_modular_dependencies`.

## Verification Commands

```bash
# Focused runtime bundling test suite
uv run pytest tests/test_runtime.py -q

# Reproduce a single Mach-O or ELF bundling case
uv run pytest tests/test_runtime.py -k "macos" -vv

# Full static + slotscheck gate
uv run ruff check . && uv run ruff format --check . && uv run mypy && uv run pyright && uv run slotscheck hatch_mojo
```
