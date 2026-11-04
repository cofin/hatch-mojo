---
type: Task
id: mojo-1-2-toolchain:t02
title: "Add mojo._package_root & .venv/Scripts binary discovery and shebang-safe win32 execution"
description: "Locate Mojo 1.2+ binaries via mojo._package_root and Windows .venv/Scripts, guard win32 sys.executable wrapping by #! shebang, and update integration Mojo syntax."
state: completed
priority: P1
verification_strategy: regression_tdd
depends_on:
  - mojo-1-2-toolchain:t01
files:
  - hatch_mojo/compiler.py
tests:
  - tests/test_compiler.py
  - tests/test_integration_compile.py
  - tests/test_integration_wheel.py
plan_revision: 3
plan_commit: 9782b0b
state_revision: 2
claimed_by: null
claimed_at: null
blocked_reason: null
unblock_condition: null
next_step: null
last_verified_at: 2026-11-04T18:26:30Z
last_verified_commit: 95de96e
verification_evidence: "RED: 4 failed, 10 passed; GREEN: 16 passed + ruff/mypy/pyright/slotscheck exit 0"
created_at: 2026-11-04T05:01:00Z
updated_at: 2026-11-04T18:26:30Z
commit: 95de96e
tags: [bugfix, compiler, discovery, windows]
---

# Task `t02`: Add `mojo._package_root` & `.venv/Scripts` Binary Discovery and Shebang-Safe `win32` Execution

## Objective

Extend `discover_mojo` to locate Mojo `1.2+` PyPI binaries via `mojo._package_root` and Windows `.venv/Scripts/`, restrict `compile_job`'s `win32` `sys.executable` wrapper strictly to `#!`-shebang scripts, and update integration test `.mojo` fixtures to Mojo `1.x` syntax.

## Context

- **Verification Strategy (`regression_tdd`)**: Fixes broken isolated-build `mojo-compiler` binary lookup, missing `.venv/Scripts/mojo.exe` lookup, and `compile_job` wrapping non-`.exe` Windows commands (`mojo.cmd`, bare `"mojo"`) in `python.exe`.
- **Invariants**: Never import `mojo` at module top level; query `importlib.import_module("mojo._package_root")` inside a helper catching `ImportError`/`AttributeError`. Keep zero inline `#` restatement comments (`HBP-08`).
- **Canonical Test Targets**: `tests/test_compiler.py`, `tests/test_integration_compile.py`, `tests/test_integration_wheel.py`.

## Steps

1. **Write failing unit and integration tests (`RED`)**:
   - In `tests/test_compiler.py`:
     - Add `test_discover_mojo_from_package_root` monkeypatching `importlib.import_module` for `"mojo._package_root"` returning an object whose `get_package_root()` points to a `tmp_path` SDK containing `bin/mojo` (and testing `get_package_root() -> None` graceful fallback), verifying `discover_mojo` returns `str(sdk / "bin/mojo")` ahead of `shutil.which`.
     - Isolate existing `test_discover_mojo_missing` and `test_discover_mojo_from_venv` (plus `test_discover_mojo_from_windows_venv_scripts` under `sys.platform = "win32"`) by monkeypatching `hatch_mojo.compiler._discover_mojo_from_package` to `lambda: None` so ambient `mojo-compiler` installs never mask `.venv`/missing fallback tests.
     - Update `mojo_bin="python3"` to `mojo_bin=sys.executable` in `test_compile_job_non_fail_fast_returns_false` and `test_compile_job_fail_fast_raises` so `windows-latest` virtualenvs (which provide `python.exe` without `python3.exe`) do not raise `FileNotFoundError` once unconditional `sys.executable` wrapping is removed.
     - Add `test_compile_job_win32_cmd_shim_not_wrapped_with_python` and `test_compile_job_win32_shebang_script_wrapped_with_python` (`sys.platform = "win32"`, mocking `subprocess.run`) proving `.cmd` / bare binary names execute directly while extensionless `#!` Python test stubs (both absolute and `root`-relative) are prefixed with `sys.executable`.
2. **Implement discovery and `win32` shebang detection (`GREEN`)**:
   - In `hatch_mojo/compiler.py`:
     - Add `_discover_mojo_from_package() -> str | None` querying `importlib.import_module("mojo._package_root").get_package_root()` inside `try ... except (ImportError, AttributeError, RuntimeError, OSError):`, guarding `if pkg_root:`, and checking `Path(pkg_root) / "bin" / ("mojo.exe" if sys.platform == "win32" else "mojo")`.
     - Update `discover_mojo(root, configured)` order: `configured` &rarr; `HATCH_MOJO_BIN` &rarr; `_discover_mojo_from_package()` &rarr; `shutil.which("mojo")` &rarr; local `.venv` candidates (`root / ".venv/Scripts/mojo.exe"`, `root / ".venv/Scripts/mojo.cmd"`, `root / ".venv/Scripts/mojo"` on `win32`; `root / ".venv/bin/mojo"` on POSIX). Update the `FileNotFoundError` message to mention `mojo-compiler` / `.venv`.
     - Add `_has_shebang(path: Path) -> bool` returning `True` iff `path.is_file()` and `path.open("rb").read(2) == b"#!"` (ignoring `OSError`).
     - In `compile_job`: on `win32`, resolve `mojo_bin` via `shutil.which(mojo_bin)` when `not (Path(mojo_bin) if Path(mojo_bin).is_absolute() else root / mojo_bin).exists()`, check `.exe`/`.cmd`/`.bat` suffixes if needed, build `command = build_command(mojo_bin, root, job)`, resolve `cmd_path = Path(command[0]) if Path(command[0]).is_absolute() else root / command[0]`, and prepend `sys.executable` **only** when `not command[0].lower().endswith((".exe", ".cmd", ".bat"))` and `_has_shebang(cmd_path)`.
   - In `tests/test_integration_compile.py` and `tests/test_integration_wheel.py`: update sample `.mojo` source strings from `fn main():` to Mojo `1.x` `def main():` / `@export def PyInit_...() abi("C") -> PythonObject:` syntax and remove inline restatement comments in modified test blocks.
3. **Refactor & verify**:
   - Run all static type/lint/slot gates and compiler/wheel test suites.

## Verification

```bash
# Initial RED check
uv run pytest tests/test_compiler.py -q

# Final GREEN + static gates (all must exit 0)
uv run ruff check . && uv run ruff format --check . && uv run mypy && uv run pyright && uv run slotscheck hatch_mojo
uv run pytest tests/test_compiler.py tests/test_integration_compile.py tests/test_integration_wheel.py -q
```

## Acceptance Criteria

- [x] `discover_mojo` resolves `mojo._package_root` (`bin/mojo`) and Windows `.venv/Scripts/mojo.{exe,cmd}` in priority order (`R3`).
- [x] `compile_job` on `win32` wraps `command` with `sys.executable` iff `command[0]` is a `#!`-shebang file, leaving `.exe`, `.cmd`, `.bat`, and `PATH` binaries unwrapped (`R3`).
- [x] Integration tests use Mojo `1.x` `def` syntax and pass end-to-end (`R3`).
- [x] `ruff`, `mypy`, `pyright`, `slotscheck`, and `pytest` exit `0`.

## Notes & Discoveries

- [2026-11-04 18:26] Patched `importlib.import_module` at the stdlib boundary in `test_discover_mojo_from_package_root` and extracted `_resolve_win32_mojo_bin` + `_has_shebang` in `hatch_mojo/compiler.py` so `win32` `.cmd`/`.bat` shims and `PATH` binaries execute without `sys.executable` wrapping.
