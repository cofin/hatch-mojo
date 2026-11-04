---
type: Task
id: mojo-1-2-toolchain:t04
title: "Migrate NOTICE.mojo-runtime to Apache-2.0 WITH LLVM-exception and UTF-8 SDK license copying"
description: "Replace Modular Community License text with Apache-2.0 WITH LLVM-exception (plus conditional MAX Section 1.5), UTF-8 encoding, and writable .dist-info LICENSE copying."
state: completed
priority: P1
verification_strategy: behavior_tdd
depends_on:
  - mojo-1-2-toolchain:t03
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
last_verified_at: 2026-11-04T18:34:32Z
last_verified_commit: 67252d3
verification_evidence: "RED: 7 failed, 2 passed; GREEN: 126 passed + ruff/mypy/pyright/slotscheck exit 0"
created_at: 2026-11-04T05:01:00Z
updated_at: 2026-11-04T18:35:00Z
commit: 67252d3
tags: [migration, runtime, licensing, apache-2-0]
---

# Task `t04`: Migrate `NOTICE.mojo-runtime` to `Apache-2.0 WITH LLVM-exception` and UTF-8 SDK License Copying

## Objective

Replace the obsolete *Modular Community License* notice in `hatch_mojo/runtime.py` with accurate `Apache-2.0 WITH LLVM-exception` attribution (with conditional `MAX License` Section 1.5 coverage when MAX libraries are bundled), explicit `encoding="utf-8"`, and PyPI `.dist-info/licenses/` SDK license lookup.

## Context

- **Verification Strategy (`behavior_tdd`)**: Updates observable contents and file-discovery behavior of `NOTICE.mojo-runtime` and `LICENSE.mojo-runtime` emitted by `bundle_runtime_libs` (`NRB-07`).
- **Primary-Source Legal Contract**: Mojo `1.0+` compiler, stdlib, and runtime (`libKGENCompilerRTShared`, `libAsyncRTMojoBindings`, `libAsyncRTRuntimeGlobals`, `libMSupportGlobals`) are licensed under `Apache-2.0 WITH LLVM-exception` (`https://github.com/modular/modular/blob/main/LICENSE`, `Copyright (c) Modular Inc, a Qualcomm Company`). Modular `26.7` introduced the `MAX License` (`https://www.modular.com/legal/max-license`), whose Section 1.5 affirms `Apache-2.0 WITH LLVM-exception` controls for Apache-licensed Mojo components.
- **Canonical Test Target**: `tests/test_runtime.py`.

## Steps

1. **Write failing unit tests (`RED`)**:
   - In `tests/test_runtime.py`: update existing notice tests and add new cases verifying:
     - `NOTICE.mojo-runtime` contains `"Apache License 2.0 with LLVM Exceptions"`, `"Apache-2.0 WITH LLVM-exception"`, `"https://github.com/modular/modular/blob/main/LICENSE"`, and `"Modular Inc, a Qualcomm Company"`, and does **not** contain `"Modular Community License"` or `"max-mojo-license"`.
     - When `lib_filenames` includes a MAX library (`"libMAXEngine.so"` or `"libMOGGKernelAPI.so"`), `NOTICE.mojo-runtime` additionally appends the `MAX License` (`https://www.modular.com/legal/max-license`, Section 1.5) paragraph; when only Mojo runtime libraries are bundled, the MAX paragraph is omitted.
     - `_find_sdk_license(modular_lib)` copies `LICENSE.mojo-runtime` (with `stat.S_IWUSR` owner-write permission even when the source SDK license is `0444`) when `LICENSE` exists at `modular_lib.parent / "LICENSE"` OR inside sibling `.dist-info` (`mojo_compiler-*.dist-info/licenses/LICENSE*`, `mojo_compiler_mojo_libs-*.dist-info/licenses/LICENSE*`, `mojo-*.dist-info/LICENSE*`).
2. **Implement updated notice template and SDK license lookup (`GREEN`)**:
   - In `hatch_mojo/runtime.py`:
     - Replace `_MOJO_RUNTIME_NOTICE` with the `Apache-2.0 WITH LLVM-exception` template (`Copyright (c) Modular Inc, a Qualcomm Company`) and add `_MAX_RUNTIME_NOTICE_ADDENDUM` referencing `https://www.modular.com/legal/max-license` and Section 1.5 separability.
     - Add `_has_max_libraries(lib_filenames: list[str]) -> bool` returning `True` when any filename starts with `("libMAX", "libMOGG")`.
     - Add `_find_sdk_license(modular_lib: Path) -> Path | None` checking `modular_lib.parent / "LICENSE"` first, then iterating sorted `modular_lib.parent.parent.glob(pattern)` across `("mojo*.dist-info/licenses/LICENSE*", "mojo*.dist-info/LICENSE*", "modular*.dist-info/licenses/LICENSE*", "modular*.dist-info/LICENSE*", "max*.dist-info/licenses/LICENSE*", "max*.dist-info/LICENSE*")`, returning the first `p.is_file()`.
     - In `_write_license_notice`: write `notice.write_text(..., encoding="utf-8")`, copy `_find_sdk_license(modular_lib)` when found, and ensure `dest.chmod(dest.stat().st_mode | stat.S_IWUSR)` (`NRB-05`).
3. **Refactor & verify**:
   - Ensure zero inline `#` restatement comments in `_write_license_notice` and run full Chapter 1 recovery checkpoint gates.

## Verification

```bash
# Initial RED check
uv run pytest tests/test_runtime.py -k "license or notice" -q

# Final GREEN + Chapter 1 Recovery Checkpoint (all must exit 0)
uv run ruff check . && uv run ruff format --check . && uv run mypy && uv run pyright && uv run slotscheck hatch_mojo
uv run pytest -q
```

## Acceptance Criteria

- [x] `NOTICE.mojo-runtime` cites `Apache-2.0 WITH LLVM-exception` and `Modular Inc, a Qualcomm Company` with zero references to `Modular Community License` (`R5`).
- [x] `MAX License` Section 1.5 addendum appears iff MAX libraries (`libMAX*` / `libMOGG*`) are bundled (`R5`).
- [x] `NOTICE.mojo-runtime` is written with explicit `encoding="utf-8"`, and `LICENSE.mojo-runtime` is copied from either `<sdk>/LICENSE` or sibling `.dist-info/licenses/` (`R5`, `NRB-07`).
- [x] Full static analysis and `pytest` suite exit `0`.

## Notes & Discoveries

- [2026-11-04 18:34] Applied `stat.S_IWUSR` to copied `LICENSE.mojo-runtime` files so read-only wheel `.dist-info/licenses/` files never obstruct subsequent cleanups or rebuilds.
