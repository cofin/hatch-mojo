---
type: Task
id: mojo-1-2-toolchain:t01
title: "Align EmitType, mojoc precompile CLI, and Mojo 0.x input validation"
description: "Anchor .gitignore /specs, replace static-lib with mojoc precompile, map executable to --emit exe, guard external paths, and reject Mojo 0.x inputs."
state: completed
priority: P1
verification_strategy: behavior_tdd
depends_on: []
files:
  - .gitignore
  - hatch_mojo/types.py
  - hatch_mojo/config.py
  - hatch_mojo/planner.py
  - hatch_mojo/compiler.py
  - hatch_mojo/artifacts.py
tests:
  - tests/test_config.py
  - tests/test_planner.py
  - tests/test_compiler.py
  - tests/test_artifacts.py
plan_revision: 3
plan_commit: 9782b0b
state_revision: 2
claimed_by: null
claimed_at: null
blocked_reason: null
unblock_condition: null
next_step: null
last_verified_at: 2026-11-04T18:22:00Z
last_verified_commit: 51de4cc
verification_evidence: "RED: 17 failed, 34 passed; GREEN: 51 passed + ruff/mypy/pyright/slotscheck exit 0"
created_at: 2026-11-04T05:01:00Z
updated_at: 2026-11-04T18:22:00Z
commit: 51de4cc
tags: [migration, mojo, cli, mojoc]
---

# Task `t01`: Align `EmitType`, `mojoc` Precompile CLI, and Mojo `0.x` Input Validation

## Objective

Replace unsupported `"static-lib"` with `"mojoc"` (`mojo precompile`), map `"executable"` to `mojo build --emit exe`, guard out-of-tree paths in `build_command`, and reject removed Mojo `0.x` constructs (`static-lib`, `.🔥`, `.mojopkg`) during configuration parsing.

## Context

- **Verification Strategy (`behavior_tdd` + `regression_tdd`)**: Introduces new `"mojoc"` precompile CLI behavior while fixing `--emit executable` &rarr; `--emit exe` and out-of-root `relative_to(root)` `ValueError` regressions at confirmed public seams (`parse_config`, `plan_jobs`, `build_command`, `register_artifacts`).
- **Invariants**: Keep `@dataclass(slots=True, frozen=True)`, PEP 585/604 types, Google-style docstrings, and zero inline `#` restatement comments (`HBP-01`, `HBP-08`). Preserve `-Xlinker -headerpad_max_install_names` on `darwin` for linkable native emits (`python-extension`, `shared-lib`, `executable`) while omitting it on `mojoc` and `object` (`HBP-04`).
- **Canonical Test Targets**: `tests/test_config.py`, `tests/test_planner.py`, `tests/test_compiler.py`, and `tests/test_artifacts.py`.

## Steps

1. **Write failing unit tests (`RED`)**:
   - In `tests/test_config.py`: add tests asserting `parse_config` accepts `emit = "mojoc"` (requiring explicit `install`), raises `ValueError` mentioning `"static-lib"` and `"Mojo 1.x"` when `emit = "static-lib"`, and raises `ValueError` when `input` or `output` ends with `".🔥"`, `"📦"`, or `".mojopkg"`.
   - In `tests/test_planner.py`: update `_get_suffix_map` assertions (`win32`, `darwin`, `linux`) to verify `"mojoc": ".mojoc"` and add `test_plan_jobs_mojoc_default_output` verifying `build/mojo/<stem>.mojoc`.
   - In `tests/test_compiler.py`: add tests asserting `build_command` emits `["mojo", "build", "--emit", "exe", ...]` for `emit="executable"`, emits `["mojo", "precompile", "-I", ..., "-D", ..., *flags, <input>, "-o", <output>]` (without `--emit` or `-headerpad_max_install_names` even on `darwin`) for `emit="mojoc"`, and succeeds when `input_path` or `output_path` lies outside `root` (e.g., `tmp_path.parent / "external_out.so"`).
   - In `tests/test_artifacts.py`: update `test_register_non_python_variants` to replace `"static-lib"` (`b.a`) with `"mojoc"` (`b.mojoc`) and add `test_register_mojoc_only_keeps_pure_python` verifying a wheel containing only `"mojoc"` / `"object"` jobs does not set `infer_tag = True` or `pure_python = False`.
2. **Implement `.gitignore` fix, types, validation, suffixes, CLI, and artifact purity (`GREEN`)**:
   - In `.gitignore`: change line 2 `specs` to `/specs` so `.agents/bundles/specs/**` is tracked cleanly by Git and ripgrep across all commits.
   - In `hatch_mojo/types.py::EmitType` and `EMIT_VALUES`: change `"static-lib"` to `"mojoc"`.
   - In `hatch_mojo/config.py::_validate_job`: before generic `EMIT_VALUES` rejection, raise `ValueError(f"Job '{name}' uses removed emit 'static-lib'; Mojo 1.x does not support static-lib (use 'object' or 'mojoc')")` when `emit_value == "static-lib"`; reject `str(input_value)` or `str(data.get("output") or "")` ending with `(".🔥", "📦", ".mojopkg")` with `ValueError` naming the removed Mojo `0.x` suffix.
   - In `hatch_mojo/planner.py::_get_suffix_map`: replace `"static-lib"` entries across all OS branches with `"mojoc": ".mojoc"`.
   - In `hatch_mojo/compiler.py::build_command`: add a helper `_format_cli_path(path: Path, root: Path) -> str` returning `str(path.relative_to(root))` when `path.is_relative_to(root)` else `str(path)`. Branch on `job.emit == "mojoc"` to construct `[mojo_bin, "precompile", ...]` with `-I`, `-D`, `*job.flags`, input, and `-o` output; for `mojo build`, map `"executable": "exe"`, `"python-extension": "shared-lib"`, `"shared-lib": "shared-lib"`, and `"object": "object"`.
   - In `hatch_mojo/artifacts.py::register_artifacts`: change `if job.emit != "object":` to `if job.emit not in {"object", "mojoc"}:` so precompiled `.mojoc` IR archives do not mark pure wheels as platform-native binaries.
3. **Refactor & verify**:
   - Ensure docstrings document the `mojo precompile` vs. `mojo build` split and run all static analysis and unit test gates.

## Verification

```bash
# Initial RED check (expect failures on new test cases)
uv run pytest tests/test_config.py tests/test_planner.py tests/test_compiler.py tests/test_artifacts.py -q

# Final GREEN + static gates (all must exit 0)
uv run ruff check . && uv run ruff format --check . && uv run mypy && uv run pyright && uv run slotscheck hatch_mojo
uv run pytest tests/test_config.py tests/test_planner.py tests/test_compiler.py tests/test_artifacts.py -q
```

## Acceptance Criteria

- [x] `EmitType` and `EMIT_VALUES` expose `("python-extension", "shared-lib", "mojoc", "object", "executable")` (`R1`).
- [x] `parse_config` rejects `"static-lib"`, `.🔥`, `📦`, and `.mojopkg` with actionable `ValueError` messages (`R1`).
- [x] `build_command` maps `"executable"` &rarr; `mojo build --emit exe`, maps `"mojoc"` &rarr; `mojo precompile` without `--emit` or Mach-O headerpad flags, and handles paths outside `root` without raising `ValueError` (`R1`, `R2`).
- [x] `register_artifacts` leaves `pure_python` / `infer_tag` unset when jobs contain only `"object"` and/or `"mojoc"` (`R1`).
- [x] `ruff`, `mypy`, `pyright`, `slotscheck`, and focused `pytest` modules exit `0`.

## Notes & Discoveries

- [2026-11-04 18:22] Checked removed Mojo `0.x` input/output suffixes (`.🔥`, `📦`, `.mojopkg`) and `emit == "static-lib"` before `module`/`install` checks in `_validate_job` so legacy inputs raise the Mojo `0.x`/`1.x` diagnostic directly even without an `install` mapping.
