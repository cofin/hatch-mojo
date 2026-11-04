---
type: Task
id: mojo-1-2-toolchain:t03
title: "Expand discover_modular_lib for mojo-compiler, wrapper venvs, and Conda/Pixi prefixes"
description: "Discover Modular runtime libraries in compiler-matched order across mojo_bin wrapper venvs, mojo._package_root, PyPI specs, and Conda/Pixi prefixes."
state: completed
priority: P1
verification_strategy: behavior_tdd
depends_on:
  - mojo-1-2-toolchain:t02
files:
  - hatch_mojo/runtime.py
tests:
  - tests/test_runtime.py
plan_revision: 3
plan_commit: 9782b0b
state_revision: 2
claimed_by: null
claimed_at: null
blocked_reason: null
unblock_condition: null
next_step: null
last_verified_at: 2026-11-04T18:30:37Z
last_verified_commit: 0465180
verification_evidence: "RED: 8 failed, 8 passed; GREEN: 53 passed + ruff/mypy/pyright/slotscheck exit 0"
created_at: 2026-11-04T05:01:00Z
updated_at: 2026-11-04T18:30:37Z
commit: 0465180
tags: [feature, runtime, discovery, pypi, pixi]
---

# Task `t03`: Expand `discover_modular_lib` for `mojo-compiler`, Wrapper Venvs, and Conda/Pixi Prefixes

## Objective

Extend `hatch_mojo/runtime.py::discover_modular_lib` so runtime library discovery succeeds with `mojo-compiler>=1.2.0` / `mojo>=1.2.0` / `max>=26.7.0` PyPI packages, external tool-venv console-script shims (`<venv>/bin/mojo`), and Conda/Pixi environments (`CONDA_PREFIX`, `.pixi`).

## Context

- **Verification Strategy (`behavior_tdd`)**: Adds observable discovery paths through the public `discover_modular_lib(root, mojo_bin)` seam while preserving `_sentinel()` (`libKGENCompilerRTShared.{so,dylib}`) validation on every candidate (`NRB-04`, `NRB-08`).
- **Why External Wrapper Venvs Failed Previously**: Under `uv`/`pip`, `<tool_venv>/bin/mojo` is a Python console script while native libraries reside at `<tool_venv>/lib/python3.X/site-packages/modular/lib/`; walking 5 parents up from `<tool_venv>/bin` checked `<tool_venv>/lib` (missing `python3.X/site-packages/modular/lib`), and `find_spec` inside an isolated PEP 517 build venv cannot see the external `tool_venv`.
- **Canonical Test Target**: `tests/test_runtime.py`.

## Steps

1. **Write failing unit tests (`RED`)**:
   - In `tests/test_runtime.py`: isolate existing fallback/missing tests (`test_discover_from_mojo_binary`, `test_discover_from_container_path`, `test_discover_not_found`) by clearing `CONDA_PREFIX` (`monkeypatch.delenv("CONDA_PREFIX", raising=False)`) and stubbing `_discover_from_package_specs` when testing lower-priority fallbacks, and add tests covering:
     - Compiler-matched priority when explicit `mojo_bin` is passed alongside an ambient `mojo._package_root` install (`mojo_bin`'s SDK wins over ambient `mojo._package_root`, preventing compiler/runtime ABI skew).
     - Discovery via `mojo._package_root.get_package_root()` returning `<sdk>` containing `lib/<sentinel>` (and graceful fallback when `get_package_root()` returns `None`).
     - Discovery via `importlib.util.find_spec("mojo")` where `spec.origin` is `<site_packages>/mojo/__init__.py` and the sentinel lives in sibling `<site_packages>/modular/lib/<sentinel>` or `<site_packages>/mojo/lib/<sentinel>`.
     - Discovery from an external wrapper `mojo_bin = "<tool_venv>/bin/mojo"` (and bare `"mojo"` resolved via `shutil.which`) where `find_spec` returns `None` and the sentinel lives at `<tool_venv>/lib/python3.12/site-packages/modular/lib/<sentinel>`, `<tool_venv>/lib64/python3.12/site-packages/modular/lib/<sentinel>` (RHEL/manylinux), `<tool_venv>/lib/python3.12/dist-packages/modular/lib/<sentinel>` (Debian), or `<tool_venv>/Lib/site-packages/modular/lib/<sentinel>` (Windows layout).
     - Discovery from `CONDA_PREFIX` env var (`$CONDA_PREFIX/lib/<sentinel>`) and `<root>/.pixi/envs/default/lib/<sentinel>`.
     - Updated `FileNotFoundError` message referencing `mojo-compiler` and `MODULAR_LIB_DIR`.
2. **Implement expanded `discover_modular_lib` (`GREEN`)**:
   - In `hatch_mojo/runtime.py`: add private helpers `_has_sentinel(candidate: Path) -> bool`, `_discover_from_package_specs() -> Path | None`, and `_discover_from_mojo_bin(mojo_bin: str) -> Path | None`, keeping `discover_modular_lib(root: Path, mojo_bin: str | None) -> Path` strictly ordered:
     1. `MODULAR_LIB_DIR` environment variable.
     2. `mojo_bin` (when `mojo_bin` is not `None`, resolving `shutil.which(mojo_bin)` first if `not Path(mojo_bin).exists()`): walk up to 6 ancestors checking `<cursor>/lib`, `<cursor>/{modular,mojo,mojo_compiler,max}/lib` (catching sibling `site-packages/modular/lib` when `mojo_bin` is `<venv>/.../site-packages/mojo/bin/mojo`), AND sorted `<cursor>/{lib/python*/site-packages,lib64/python*/site-packages,lib/python*/dist-packages,Lib/site-packages}/{modular,mojo,mojo_compiler,max}/lib` so bundled runtime libraries always match the active `mojo_bin`.
     3. `importlib.import_module("mojo._package_root").get_package_root()` (inside `try ... except (ImportError, AttributeError, RuntimeError, OSError):` with `if pkg_root:`) &rarr; `Path(pkg_root) / "lib"`.
     4. `importlib.util.find_spec` across `("mojo", "mojo_compiler", "max", "modular")`: inspect `<origin.parent>/lib`, `<submodule_loc>/lib`, and `<site_packages>/{modular,mojo,mojo_compiler,max}/lib` (where `<site_packages>` is `origin.parent.parent` or `Path(submodule_loc).parent`).
     5. Environment and workspace fallbacks: `Path(os.environ["CONDA_PREFIX"]) / "lib"` (when `CONDA_PREFIX` is set), `Path("/opt/modular/lib")`, `root / ".pixi" / "envs" / "default" / "lib"`, and `root / ".modular" / "lib"`.
   - Raise `FileNotFoundError("Could not locate Mojo runtime libraries (libKGENCompilerRTShared). Add 'mojo-compiler>=1.2.0' to build-system.requires or set MODULAR_LIB_DIR.")` when all candidates miss.
3. **Refactor & verify**:
   - Remove any inline `#` restatement comments in touched functions (moving search-order documentation into Google-style docstrings) and run full verification gates.

## Verification

```bash
# Initial RED check
uv run pytest tests/test_runtime.py -k "discover" -q

# Final GREEN + static gates (all must exit 0)
uv run ruff check . && uv run ruff format --check . && uv run mypy && uv run pyright && uv run slotscheck hatch_mojo
uv run pytest tests/test_runtime.py -q
```

## Acceptance Criteria

- [x] `discover_modular_lib` locates `_sentinel()` across `MODULAR_LIB_DIR`, `mojo._package_root`, `mojo`/`mojo_compiler`/`max`/`modular` specs, external `<venv>/bin/mojo` wrapper site-packages, `CONDA_PREFIX`, `/opt/modular/lib`, `.pixi`, and `.modular` (`R4`).
- [x] Every candidate directory is verified with `(candidate / _sentinel()).exists()` before returning (`R4`, `NRB-04`).
- [x] `FileNotFoundError` directs users to `mojo-compiler>=1.2.0` and `MODULAR_LIB_DIR` (`R4`).
- [x] `ruff`, `mypy`, `pyright`, `slotscheck`, and `tests/test_runtime.py` exit `0`.

## Notes & Discoveries

- [2026-11-04 18:30] Ordered explicit `mojo_bin` lookup ahead of ambient `mojo._package_root` and `find_spec` in `discover_modular_lib` so custom/external compilers always bundle their matching runtime ABI.
