---
type: Task
id: wheel-tags-metadata-and-ci:t03
title: "Rewrite README.md for Mojo 1.2+ / cibuildwheel 4.x and synchronize .agents/skills/ invariants"
description: "Update README.md for Mojo 1.2+, wheel-tag, editable/cache defaults, and cibuildwheel 4.x, and synchronize .agents/skills/ and knowledge chapters."
state: completed
priority: P2
verification_strategy: documentation_validation
depends_on:
  - wheel-tags-metadata-and-ci:t02
files:
  - README.md
  - .agents/skills/hatch-build-pipeline/SKILL.md
  - .agents/skills/hatch-build-pipeline/references/architecture-and-patterns.md
  - .agents/skills/hatch-build-pipeline/references/verification.md
  - .agents/skills/review-hatch-build-pipeline/references/checklist.md
  - .agents/skills/review-hatch-build-pipeline/references/false-positive-suppressions.md
  - .agents/skills/native-runtime-bundling/SKILL.md
  - .agents/skills/native-runtime-bundling/references/elf-and-macho-linking.md
  - .agents/skills/native-runtime-bundling/references/verification.md
  - .agents/skills/review-native-runtime-bundling/references/checklist.md
  - .agents/skills/review-native-runtime-bundling/references/false-positive-suppressions.md
  - .agents/bundles/knowledge/architecture/build-pipeline-seams.md
  - .agents/bundles/knowledge/domains/mojo-wheel-packaging.md
  - .agents/bundles/knowledge/gotchas/platform-linking-and-build-quirks.md
tests: []
plan_revision: 3
plan_commit: 7e10d5b
state_revision: 2
claimed_by: null
claimed_at: null
blocked_reason: null
unblock_condition: null
next_step: null
last_verified_at: 2026-11-04T20:38:00Z
last_verified_commit: 19d20d7
verification_evidence: "uv run pytest --cov -q (179 passed, 100.00% statement and branch coverage); ruff, mypy, pyright, slotscheck exit 0; git grep stale-reference audit exit 1 (0 matches)"
created_at: 2026-11-04T05:12:00Z
updated_at: 2026-11-04T20:38:00Z
commit: 19d20d7
tags: [docs, readme, cibuildwheel, skills, mojo-1-2]
---

# Task `t03`: Rewrite `README.md` for Mojo `1.2+` / `cibuildwheel 4.x` and Synchronize `.agents/skills/` Invariants

## Objective

Update `README.md` and project-local `.agents/skills/` reference documents so user onboarding, `cibuildwheel 4.x` recipes, and agent review checklists accurately reflect `hatch-mojo v0.2.0` and Mojo `1.2+` (`Apache-2.0 WITH LLVM-exception`).

## Context

- **Verification Strategy (`documentation_validation`)**: Audits every TOML/CLI snippet, option table entry, and skill rule against live `hatch_mojo/{config,types,planner,compiler,runtime,artifacts,cleaning,plugin}.py` signatures and runs the full repository `make check-all` equivalent gate.
- **Key Stale Claims to Eliminate**:
  - `static-lib` emit type &rarr; replaced by `mojoc` (`mojo precompile` `.mojoc` archives).
  - `skip-editable = true` default &rarr; now `false` (`HATCH_MOJO_SKIP_EDITABLE=1` opt-out) with zero-copy persistent SDK RPATHs.
  - `Modular Community License` in runtime bundling docs &rarr; now `Apache-2.0 WITH LLVM-exception` (`Modular Inc, a Qualcomm Company`) with `MAX License` Section 1.5 supplement only when MAX libraries are bundled.
  - `python -m wheel tags` in `cibuildwheel` Linux repair command &rarr; breaks on `cibuildwheel 4.x` because `wheel` is no longer preinstalled; replace with `uvx wheel tags --remove --platform-tag manylinux_2_34_x86_64 {wheel} && mv {wheel} {dest_dir}` plus `manylinux-x86_64-image = "manylinux_2_34"`, `build-frontend = "uv"`, `skip = "cp31?t-* pp* *-musllinux*"`, and `macos-latest` (`arm64`) guidance.

## Steps

1. **Update `README.md` for Mojo `1.2+`, `mojo-compiler`, `wheel-tag`, editable & cache defaults, and `cibuildwheel 4.x`**:
   - Show isolated PEP 517 `[build-system]` setup (`requires = ["hatchling>=1.31.0,!=1.32.3", "hatch-mojo", "mojo-compiler>=1.2.0"]`) alongside Pixi/local `mojo` usage and a minimal Mojo `1.2+` `std.python.bindings` `PyInit_<name>` example.
   - Document all Global Options (`mojo-bin`, `parallel`, `fail-fast`, `cache`, `wheel-tag`, `bundle-libs`, `skip-editable`, `clean-before-build`, `clean-after-build`, `build-dir`, `targets`, `include`, `exclude`) and environment variable overrides (`HATCH_MOJO_BIN`, `HATCH_MOJO_CACHE`, `HATCH_MOJO_SKIP_EDITABLE`, `HATCH_MOJO_WHEEL_TAG`).
   - Document `emit` types (`python-extension`, `shared-lib`, `mojoc`, `object`, `executable`), `{stem}` templating on multi-file globs, trailing-`/` directory vs exact-file `install.path` semantics (`scripts`, `data`, `force-include`), deep profile merging, `wheel-tag = "py3-none"` (including the `cp313t`/`cp314t` GIL note), `Apache-2.0 WITH LLVM-exception` runtime bundling across extensions/executables/shared-libs, and `cibuildwheel 4.x` recipes.
2. **Synchronize `.agents/skills/` and `.agents/bundles/knowledge/` invariants with `v0.2.0` contracts**:
   - Update `.agents/skills/hatch-build-pipeline/SKILL.md`, `references/architecture-and-patterns.md`, and `references/verification.md` (`MojoBuildHook.finalize` cleanup, `editable-manifest.json`, `mojoc` precompile, `shared_scripts`/`shared_data` + `bypass-selection`, `wheel-tag` policy, `{stem}` globs, `cache.json` + `.raw`, `patch_editable_runtime`, shebang-guarded `win32`).
   - Update `.agents/skills/review-hatch-build-pipeline/references/checklist.md` (`HBP-03` updated for `mojoc`/`object` purity and `wheel-tag = "auto" | "infer" | "py3-none" | "<tag>"`) and `references/false-positive-suppressions.md` (`FP-HBP-03` updated to shebang-guarded `win32` `sys.executable` wrapping).
   - Update `.agents/skills/native-runtime-bundling/SKILL.md`, `references/elf-and-macho-linking.md`, `references/verification.md`, `.agents/skills/review-native-runtime-bundling/references/checklist.md`, and `references/false-positive-suppressions.md` (`FP-NRB-02` `RuntimeBundleResult({}, {}, ())` / `()`; `macos-latest` CI runner note; compiler-matched `mojo_bin` + `mojo._package_root` SDK discovery; `RuntimeBundleResult` across `platlib` and `shared_data` `lib/<dist>.libs/`; `patch_editable_runtime` + `_is_ephemeral_sdk`; `_patch_macos_extension` `_strip_absolute_rpaths` + `shared-lib` `-id`; `_patch_rpath` Darwin `_resign_ad_hoc`; and `Apache-2.0 WITH LLVM-exception` `NOTICE.mojo-runtime`).
   - Synchronize `<!-- truth: start -->` and prose sections in `.agents/bundles/knowledge/{architecture/build-pipeline-seams,domains/mojo-wheel-packaging,gotchas/platform-linking-and-build-quirks}.md` (updating `verified:` commit metadata) so OKF bundle knowledge reflects `v0.2.0`.
3. **Run full end-to-end repository verification**:
   - Verify zero stale references (`rg "static-lib|Modular Community License|python -m wheel tags" README.md .agents/skills/ .agents/bundles/knowledge/`) and execute the complete lint, typecheck, slotscheck, build, and coverage test gate.

## Verification

```bash
uv run ruff check . && uv run ruff format --check . && uv run mypy && uv run pyright && uv run slotscheck hatch_mojo
uv run pytest --cov -q
```

## Acceptance Criteria

- [x] `README.md` accurately documents Mojo `1.2+` (`mojo-compiler>=1.2.0`, `mojoc`, `wheel-tag`, `skip-editable = false`, `cache = true`, `{stem}`, `Apache-2.0 WITH LLVM-exception` bundling, and `cibuildwheel 4.x` `manylinux_2_34` + `uvx wheel tags`) with zero stale `static-lib` or `Modular Community License` claims (`R3`).
- [x] `.agents/skills/` `SKILL.md` and `references/*.md` files reflect `v0.2.0` pipeline and runtime-bundling invariants (`R3`).
- [x] Full lint, typecheck, `slotscheck`, and `pytest --cov` verification gate exits `0`.

## Notes & Discoveries

- Added comprehensive public-seam unit tests and pruned unreachable defensive guards in `7a96a66` so `covdefaults` (`fail-under = 100`, `branch = true`) passes at `100.00%` (`179 passed`).
