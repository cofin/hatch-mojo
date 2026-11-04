---
type: Task
id: hatchling-lifecycle-and-bundling:t03
title: "Fix depth-0 RPATH formatting and scope macOS _strip_absolute_rpaths to LC_RPATH across dylibs and extensions"
description: "Fix depth-0 RPATH double slashes, scope _strip_absolute_rpaths to cmd LC_RPATH blocks, strip absolute RPATHs on macOS extensions, and re-sign _patch_rpath on Darwin."
state: pending
priority: P1
verification_strategy: regression_tdd
depends_on:
  - hatchling-lifecycle-and-bundling:t02
files:
  - hatch_mojo/runtime.py
tests:
  - tests/test_runtime.py
plan_revision: 3
plan_commit: null
state_revision: 0
claimed_by: null
claimed_at: null
blocked_reason: null
unblock_condition: null
next_step: null
last_verified_at: null
last_verified_commit: null
verification_evidence: null
created_at: 2026-11-04T05:03:00Z
updated_at: 2026-11-04T06:13:00Z
commit: null
tags: [bugfix, macos, mach-o, rpath, runtime]
---

# Task `t03`: Fix Depth-0 RPATH Formatting and Scope macOS `_strip_absolute_rpaths` to `LC_RPATH` Across Dylibs and Extensions

## Objective

Eliminate malformed `"$ORIGIN//..."` RPATHs on top-level (`depth == 0`) artifacts, restrict `_strip_absolute_rpaths` strictly to `cmd LC_RPATH` load commands in `otool -l` output, and strip residual absolute SDK RPATHs on macOS extensions as well as bundled dylibs.

## Context

- **Verification Strategy (`regression_tdd`)**: Reproduces and fixes three `runtime.py` defects at `tests/test_runtime.py` boundaries while preserving all `NRB-01..NRB-06` invariants (`_run_install_name_tool` idempotency and trailing `_resign_ad_hoc`).
- **Canonical Test Target**: `tests/test_runtime.py`.

## Steps

1. **Write failing regression tests (`RED`)**:
   - In `tests/test_runtime.py`:
     - Add `test_rpath_depth_0_linux` and `test_rpath_depth_0_darwin` calling `_compute_extension_rpath("_core", "_core")` and asserting `["$ORIGIN", "$ORIGIN/_core.libs"]` and `["@loader_path", "@loader_path/_core.libs"]` (no `//`).
     - Add `test_strip_absolute_rpaths_ignores_non_lc_rpath_blocks` feeding realistic `otool -l` stdout containing `cmd LC_LOAD_DYLIB` with a line containing `path /usr/local/something` alongside `cmd LC_RPATH` with `path /opt/modular/lib (offset 12)`, asserting `_run_install_name_tool` only deletes `/opt/modular/lib`.
     - Update existing `test_patch_macos_extension_rewrites_refs_and_adds_rpath` (`calls[0]` becomes `otool -l`) and `test_patch_macos_extension_skips_existing_rpath` (`call_count` `3` &rarr; `4`) plus `test_patch_rpath_darwin` (asserting trailing `codesign -s - -f`), and add `test_patch_macos_extension_strips_residual_absolute_rpaths` verifying `_patch_macos_extension` runs `otool -l` and deletes residual `/opt/modular/lib` `LC_RPATH` entries before adding `@loader_path` RPATHs and calling `codesign -s - -f`.
2. **Implement RPATH, `LC_RPATH` scoping, and `_patch_rpath` re-signing fixes (`GREEN`)**:
   - In `hatch_mojo/runtime.py`:
     - Add `_compute_relative_rpath(depth: int, libs_rel_path: str) -> list[str]` using `origin = "@loader_path" if sys.platform == "darwin" else "$ORIGIN"`: when `depth <= 0`, return `[origin, f"{origin}/{libs_rel_path.lstrip('/')}"]`; when `depth >= 1`, `up = "/".join(".." for _ in range(depth))` &rarr; `[origin, f"{origin}/{up}/{libs_rel_path.lstrip('/')}"]`. Delegate `_compute_extension_rpath(module, pkg_name)` to `_compute_relative_rpath(len(module.split(".")) - 1, f"{pkg_name}.libs")`.
     - In `_strip_absolute_rpaths(target: Path)`: track `in_lc_rpath = False` across `result.stdout.splitlines()` (`stripped == "cmd LC_RPATH"` sets `True`; `stripped.startswith("Load command ")` or (`stripped.startswith("cmd ")` and `stripped != "cmd LC_RPATH"`) sets `False`), and extract `rpath = stripped.split("path ", 1)[1].split(" (offset", 1)[0].strip()` only when `in_lc_rpath and stripped.startswith("path ")`.
     - In `_patch_macos_extension`: call `_strip_absolute_rpaths(ext)` first before rewriting linked libraries, adding `rpaths`, and calling `_resign_ad_hoc(ext)`.
     - In `_patch_rpath`: call `_resign_ad_hoc(target)` after the `-add_rpath` loop on `sys.platform == "darwin"` (`NRB-01`).
3. **Refactor & verify**:
   - Confirm zero inline `#` restatement comments and run all static and runtime test gates.

## Verification

```bash
# Initial RED check
uv run pytest tests/test_runtime.py -q

# Final GREEN + static gates (all must exit 0)
uv run ruff check . && uv run ruff format --check . && uv run mypy && uv run pyright && uv run slotscheck hatch_mojo
uv run pytest tests/test_runtime.py -q
```

## Acceptance Criteria

- [ ] `_compute_extension_rpath("_core", "_core")` emits `["$ORIGIN", "$ORIGIN/_core.libs"]` on Linux and `["@loader_path", "@loader_path/_core.libs"]` on macOS (`R3`).
- [ ] `_strip_absolute_rpaths` deletes non-`@` paths exclusively from `cmd LC_RPATH` load commands (`R3`, `NRB-03`).
- [ ] `_patch_macos_extension` strips residual absolute SDK RPATHs prior to adding `@loader_path` RPATHs and re-signing (`R3`, `NRB-01`).
- [ ] `ruff`, `mypy`, `pyright`, `slotscheck`, and `tests/test_runtime.py` exit `0`.

## Notes & Discoveries

_None._
