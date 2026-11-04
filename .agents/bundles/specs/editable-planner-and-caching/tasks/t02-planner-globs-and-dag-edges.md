---
type: Task
id: editable-planner-and-caching:t02
title: "Add pathspec glob filtering, {stem} multi-input outputs, and expanded depends-on DAG edges"
description: "Evaluate GitIgnoreSpec globs across literal and globbed jobs, expand {stem} output/module/install templates with collision checks, and rewrite depends-on DAG edges."
state: completed
priority: P1
verification_strategy: regression_tdd
depends_on:
  - editable-planner-and-caching:t01
files:
  - hatch_mojo/config.py
  - hatch_mojo/planner.py
tests:
  - tests/test_config.py
  - tests/test_planner.py
  - tests/test_plugin.py
plan_revision: 3
plan_commit: ad4930f
state_revision: 2
claimed_by: agent:executor
claimed_at: 2026-11-04T19:41:00Z
blocked_reason: null
unblock_condition: null
next_step: null
last_verified_at: 2026-11-04T19:46:07Z
last_verified_commit: 6616de5
verification_evidence: "uv run pytest tests/test_config.py tests/test_planner.py tests/test_plugin.py -q (55 passed); ruff/mypy/pyright/slotscheck exit 0"
created_at: 2026-11-04T05:05:00Z
updated_at: 2026-11-04T19:46:07Z
commit: 6616de5
tags: [bugfix, planner, globs, dag, pathspec]
---

# Task `t02`: Add `pathspec` Glob Filtering, `{stem}` Multi-Input Outputs, and Expanded `depends-on` DAG Edges

## Objective

Use `pathspec.GitIgnoreSpec` for git-style `**` `include`/`exclude` filtering across literal and globbed inputs, support `{stem}` templating to prevent multi-file glob output collisions, expand base glob job names in downstream `depends-on` edges, and remove `# type: ignore` from `_platform_match`.

## Context

- **Verification Strategy (`regression_tdd`)**: Reproduces multi-file glob output collisions, broken `depends-on` edges referencing globbed jobs, and `**` zero-directory `include`/`exclude` mismatches on Python `3.10`+.
- **Invariants**: `pathspec` is provided transitively by `hatchling>=1.31.0`; add `"types-pathspec"` or verify `pathspec` ships `py.typed` (note `pathspec>=0.12` ships `py.typed` natively in `.venv`!). Keep topological sort deterministic (`HBP-05`).
- **Canonical Test Targets**: `tests/test_planner.py`, `tests/test_config.py`.

## Steps

1. **Write failing unit tests (`RED`)**:
   - In `tests/test_planner.py`:
     - Update `test_plan_jobs_glob_multi_inputs` to use `"module": "pkg._{stem}"` and assert distinct `output_path` (`build/mojo/pkg/_a.so`, `build/mojo/pkg/_b.so`) and `module` (`"pkg._a"`, `"pkg._b"`), plus add `test_plan_jobs_glob_collision_rejected` asserting `ValueError` when multi-file globs collide on `output_path` (including recursive `src/**/kernel.mojo` matching `src/cpu/kernel.mojo` and `src/gpu/kernel.mojo` with `output=None`) or collide on `resolve_install_target` (e.g., `install = {"kind": "scripts", "path": "my-cli"}` without `{stem}`).
     - Add `test_plan_jobs_glob_and_excluded_literal_depends_on_rewrites` verifying a downstream job with `depends-on = ["kernels", "excluded_helper"]` expands `"kernels"` to `("kernels[1]", "kernels[2]")` and drops `"excluded_helper"` (`excluded_jobs`) without raising `"unknown dependencies"`.
     - Add `test_plan_jobs_git_style_include_exclude_on_glob_inputs` verifying `include = ["src/mo/**/*.mojo"]` and `exclude = ["**/experimental*.mojo"]` filter zero-directory (`src/mo/a.mojo`) and nested (`src/mo/sub/experimental_b.mojo`) glob matches cleanly.
   - In `tests/test_config.py` and `tests/test_plugin.py`: verify `parse_config` raises `"No build jobs resolved"` when raw `jobs`/`sources` is empty while returning `jobs=(), excluded_jobs=("...",)` when all literal jobs are filtered by `include`/`exclude`, and keep `_config()` in `tests/test_plugin.py` aligned with `excluded_jobs: tuple[str, ...] = ()`.
2. **Implement `pathspec` filtering, `{stem}` resolution, and `depends_on` rewrite (`GREEN`)**:
   - In `hatch_mojo/config.py::parse_config`: add `excluded_jobs: tuple[str, ...] = ()` to `HookConfig`; raise `"No build jobs resolved"` when raw `jobs_raw` is empty (and `target_name in targets`), and record literal job names filtered by `GitIgnoreSpec` in `excluded_jobs` (deferring globbed `job.input` strings containing `*?[]` to `planner.py`).
   - In `hatch_mojo/planner.py`:
     - In `_platform_match`: replace `default_environment()` + `# type: ignore[arg-type]` with `return not (job.marker and not Marker(job.marker).evaluate())`.
     - Add `_matches_filters(rel_posix: str, include: tuple[str, ...], exclude: tuple[str, ...]) -> bool` using `pathspec.GitIgnoreSpec.from_lines`.
     - Initialize `expanded_names: dict[str, tuple[str, ...]] = dict.fromkeys(config.excluded_jobs, ())` in `_expand_all_jobs`. After `_expand_inputs` (raising `ValueError` if disk glob matched zero files), filter `input_paths` through `_matches_filters`; if filtered `input_paths` is empty, record `expanded_names[job.name] = ()` and `continue`.
     - Substitute `{stem}` with `input_path.stem` in `resolved_module`, `resolved_output`, and `resolved_install_path` (supported on single-file and multi-file jobs). Reject duplicate `output_path` or duplicate `(build_job.install_kind, resolve_install_target(build_job))` across expanded `BuildJob` items with `ValueError` (`hatch_mojo.artifacts.resolve_install_target`).
     - Record `expanded_names[job.name] = tuple(concrete_names)` for every expanded job (and `()` for platform-skipped or exclude-filtered jobs), then rewrite `depends_on` across all `BuildJob` items replacing any `dep` in `expanded_names` with `*expanded_names[dep]` while leaving truly unknown `dep` names intact so `_validate_deps` still raises `ValueError("unknown dependencies")`.
3. **Refactor & verify**:
   - Run all static gates (`ruff`, `mypy`, `pyright`, `slotscheck`) and `tests/test_config.py` + `tests/test_planner.py`.

## Verification

```bash
# Initial RED check
uv run pytest tests/test_config.py tests/test_planner.py -q

# Final GREEN + static gates (all must exit 0)
uv run ruff check . && uv run ruff format --check . && uv run mypy && uv run pyright && uv run slotscheck hatch_mojo
uv run pytest tests/test_config.py tests/test_planner.py -q
```

## Acceptance Criteria

- [x] `include` and `exclude` support git-style `**` zero-or-more-directory globs across both literal and globbed `input` patterns (`R2`).
- [x] Multi-file globs expand `{stem}` into distinct `module` and `output_path` targets and raise `ValueError` on colliding fixed modules/outputs (`R2`, `HBP-05`).
- [x] Downstream `depends-on` references to globbed or platform-filtered job names rewrite cleanly without false `"unknown dependencies"` errors, while genuinely unknown job names still raise `ValueError` (`R2`, `HBP-05`).
- [x] `ruff`, `mypy`, `pyright`, `slotscheck`, and focused `pytest` modules exit `0`.

## Notes & Discoveries

_None._
