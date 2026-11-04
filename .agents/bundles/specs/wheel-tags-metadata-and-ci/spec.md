---
type: Spec
flow_id: wheel-tags-metadata-and-ci
title: "Wheel Tag Policy, PEP 639 Metadata, Docs & Multi-OS CI"
description: "Add wheel-tag (auto/infer/py3-none/<pep425_tag>) support, migrate repository metadata to PEP 639 with MIT LICENSE, expand CI to macOS and Python 3.15, and align README and skills with Mojo 1.2+."
state: completed
parent_prd: v0-2-overhaul
research:
  - ../v0-2-overhaul/research/mojo-packaging-landscape-audit_20261104.md
plan_revision: 3
plan_commit: 7e10d5b
state_revision: 4
current_task: null
last_verified_checkpoint: 19d20d7
created_at: 2026-11-04T05:12:00Z
updated_at: 2026-11-04T20:38:00Z
tags: [feature, wheel-tag, pep639, ci, cibuildwheel]
---

# Flow: Wheel Tag Policy, PEP 639 Metadata, Docs & Multi-OS CI

## 1. Specification & Context

### 1.1 Problem Statement & Objectives
With Mojo `1.2+` compiler CLI, Hatchling `1.33+` lifecycle, runtime bundling, editable installs, and SHA-256 caching complete after Chapters 1–3, four packaging and ecosystem gaps remain:
1. **Hardcoded interpreter-specific wheel tags**: `register_artifacts` unconditionally sets `build_data["infer_tag"] = True` for every native wheel (`cp312-cp312-<platform>`). Standalone CLI/shared-lib wheels with zero CPython ABI coupling are needlessly forced into per-Python-minor builds, and `python-extension` authors cannot opt into Mojo `1.2+`'s dynamic `dlopen`/`dlsym` `libpython` ABI (`py3-none-<platform>`) to collapse 5-version CI matrices into 1 build per OS/arch.
2. **Legacy PEP 621 license metadata & missing `LICENSE` file**: `pyproject.toml` still uses `license = { text = "MIT" }` with the deprecated `"License :: OSI Approved :: MIT License"` classifier while omitting a root `LICENSE` file and Python `3.15` classifier, and `Makefile` hard-pins `uv python pin 3.10` and references obsolete `.hatch_mojo`.
3. **Missing `macos-latest` and Python `3.15` CI coverage**: `.github/workflows/ci.yml` omits `macos-latest` and `"3.15"`, leaving Darwin path/tag/bundling logic untested on real macOS runners, while `publish.yml` stops at Python `3.13`.
4. **Outdated `0.26.x` user documentation & project skills**: `README.md` still documents `static-lib`, `skip-editable = true`, `Modular Community License`, and `python -m wheel tags` (which breaks on `cibuildwheel 4.x` where `wheel` is no longer preinstalled), and `.agents/skills/` still encode `v0.1.8` `HBP`/`NRB` rules.

**Objectives**: Implement `wheel-tag = "auto" | "infer" | "py3-none" | "<pep425_tag>"`, migrate `hatch-mojo` to PEP 639 with a canonical root `LICENSE` file and `macos-latest` + Python `3.15` CI, and update `README.md` and `.agents/skills/` for Mojo `1.2+`, `mojo-compiler`, and `cibuildwheel 4.x`.

**Non-Goals**: Automatic `.pyi` stub generation, native Windows Mojo runtime DLL bundling, and cross-compilation linker toolchains (deferred to PRD Backlog).

### 1.2 Upstream Execution Baseline
- **Branch**: `main`
- **Parent PRD**: [`v0-2-overhaul`](../v0-2-overhaul/spec.md) (Chapter 4 of 4)
- **Prerequisite Child Flow**: [`editable-planner-and-caching`](../editable-planner-and-caching/spec.md)

### 1.3 Code Analysis & Seam Summary

| Area | Files Examined (`path/to/file::Symbol`) | Public Seam, Dependency Category & Integration |
| --- | --- | --- |
| Wheel Tag Config | `hatch_mojo/config.py::HookConfig`, `parse_config`, `_validate_wheel_tag` | In-process TOML/env parser validating `"auto"`, `"infer"`, `"py3-none"`, or 3-segment PEP 425 tags via `packaging.tags.parse_tag`. |
| Wheel Tag Routing | `hatch_mojo/artifacts.py::resolve_host_platform_tag`, `register_artifacts`, `hatch_mojo/plugin.py::MojoBuildHook.initialize` | Local-substitutable Hatchling `build_data` seam setting `pure_python`, `infer_tag`, and `tag` (honoring `hatchling.builders.macos.process_macos_plat_tag` on `darwin`). |
| Metadata & CI | `LICENSE`, `pyproject.toml`, `Makefile`, `.github/workflows/ci.yml`, `.github/workflows/publish.yml` | Static packaging metadata (PEP 639), developer `Makefile`, and GitHub Actions multi-OS/Python `3.10`–`3.15` matrices. |
| Docs & Skills | `README.md`, `.agents/skills/{hatch-build-pipeline,native-runtime-bundling,review-*}/**`, `.agents/bundles/knowledge/**` | Consumer documentation for Mojo `1.2+` / `cibuildwheel 4.x` and synchronized agent skill/knowledge invariants. |

### 1.4 Relevant Patterns, Domain Terms & Knowledge Chapters
- Architecture & Domain: [`build-pipeline-seams.md`](../../knowledge/architecture/build-pipeline-seams.md), [`mojo-wheel-packaging.md`](../../knowledge/domains/mojo-wheel-packaging.md)
- Patterns & Testing: [`typed-slotted-models.md`](../../knowledge/patterns/typed-slotted-models.md), [`public-seam-verification.md`](../../knowledge/testing/public-seam-verification.md)
- Project Skills: [`hatch-build-pipeline`](../../../skills/hatch-build-pipeline/SKILL.md), [`native-runtime-bundling`](../../../skills/native-runtime-bundling/SKILL.md)

## 2. Requirements & Architecture

### 2.1 Functional Requirements
- **R1 (`wheel-tag` Policy & Platform Tag Resolution)**:
  - Add `wheel_tag: str = "auto"` to `HookConfig` (`wheel-tag` / `wheel_tag` in `pyproject.toml`, overridable via `HATCH_MOJO_WHEEL_TAG`). Validate non-empty strings accepting `"auto"`, `"infer"`, `"py3-none"`, or any valid 3-component PEP 425 tag (`len(tag.split("-")) == 3` and `packaging.tags.parse_tag(tag)`), raising `TypeError` for non-strings and `ValueError` for invalid tag strings.
  - Extend `register_artifacts(*, root: Path, build_data: dict[str, Any], jobs: list[BuildJob], target_name: str, wheel_tag: str = "auto", macos_max_compat: bool = False) -> None`:
    - When `target_name == "wheel"` and `has_native` (`any(job.emit not in {"object", "mojoc"} for job in jobs)`): set `build_data["pure_python"] = False`. Resolve `"auto"` to `"infer"` when any job has `emit == "python-extension"`, otherwise to `"py3-none"` (standalone `executable` / `shared-lib` wheels).
    - For effective policy `"infer"`: set `build_data["infer_tag"] = True`.
    - For effective policy `"py3-none"`: set `build_data["infer_tag"] = False` and `build_data["tag"] = f"py3-none-{resolve_host_platform_tag(macos_max_compat=macos_max_compat)}"`, where `resolve_host_platform_tag` selects the first non-`manylinux`/non-`musllinux` tag from `packaging.tags.sys_tags()` and normalizes Darwin tags via `hatchling.builders.macos.process_macos_plat_tag(plat, compat=macos_max_compat)`.
    - For an explicit `<pep425_tag>`: set `build_data["infer_tag"] = False` and `build_data["tag"] = wheel_tag` (even when `has_native` is `False`, leaving `pure_python` untouched if no native jobs exist).
  - Forward `wheel_tag=config.wheel_tag` and `macos_max_compat=bool(getattr(getattr(self, "build_config", None), "macos_max_compat", False))` from `MojoBuildHook.initialize` (`version != "editable"`).
- **R2 (PEP 639 Metadata, `LICENSE`, `Makefile`, & Multi-OS CI)**:
  - Add root MIT `LICENSE` file (`Copyright (c) 2025-present Cody Fincher`).
  - Migrate `pyproject.toml` from `license = { text = "MIT" }` to PEP 639 `license = "MIT"` and `license-files = ["LICENSE"]`, drop `"License :: OSI Approved :: MIT License"`, and add `"Programming Language :: Python :: 3.15"` to `classifiers`.
  - Remove `uv python pin 3.10` and obsolete `.hatch_mojo` from `Makefile`.
  - Expand `.github/workflows/ci.yml` `test` matrix to `os: [ubuntu-latest, macos-latest, windows-latest]` and `python-version: ["3.10", "3.11", "3.12", "3.13", "3.14", "3.15"]`, and expand `.github/workflows/publish.yml` `test-install` `python-version` to `["3.10", "3.12", "3.13", "3.14", "3.15"]`.
- **R3 (Mojo `1.2+` & `cibuildwheel 4.x` Documentation & Skill Synchronization)**:
  - Update `README.md` for Mojo `1.2+`: `[build-system] requires = ["hatchling>=1.31.0,!=1.32.3", "hatch-mojo", "mojo-compiler>=1.2.0"]` isolated builds, `mojoc` (`mojo precompile`) vs `executable`/`shared-lib`/`python-extension`/`object`, `wheel-tag` (`auto`/`infer`/`py3-none` + free-threaded `cp313t`/`cp314t` GIL note), `skip-editable = false` + `HATCH_MOJO_SKIP_EDITABLE`, `cache = true` + `HATCH_MOJO_CACHE`, `{stem}` multi-file globs, `Apache-2.0 WITH LLVM-exception` `NOTICE.mojo-runtime` bundling across extensions/executables/shared-libs, and `cibuildwheel 4.x` config (`manylinux_2_34`, `uvx wheel tags`, `cp31?t-*` skip guidance, `macos-latest` `arm64`).
  - Synchronize `.agents/skills/{hatch-build-pipeline,native-runtime-bundling,review-hatch-build-pipeline,review-native-runtime-bundling}/**` with `v0.2.0` contracts so automated reviews and future flows enforce current invariants.

### 2.2 Public Interfaces, Deep Modules & Seam Contracts
- `hatch_mojo/config.py::HookConfig.wheel_tag: str` (default `"auto"`).
- `hatch_mojo/artifacts.py::resolve_host_platform_tag(*, macos_max_compat: bool = False) -> str` and `register_artifacts(*, root: Path, build_data: dict[str, Any], jobs: list[BuildJob], target_name: str, wheel_tag: str = "auto", macos_max_compat: bool = False) -> None`.

### 2.3 Non-Functional & Safety Constraints
- Match Hatchling's `WheelBuilder.get_best_matching_tag()` platform selection (`skip manylinux/musllinux` + `process_macos_plat_tag`) byte-for-byte so `"py3-none"` produces identical platform tags to Hatchling's native wheels across Linux, macOS (`MACOSX_DEPLOYMENT_TARGET` / `ARCHFLAGS`), and Windows.
- Keep `HookConfig` `@dataclass(slots=True, frozen=True)` and maintain zero inline `#` restatement comments.

### 2.4 Acceptance Scenarios (Given / When / Then)
- **Scenario 1 (`wheel-tag = "auto"` standalone CLI vs extension)**: Given a wheel with only `emit = "executable"` (`install.kind = "scripts"`), when `uv build --wheel` runs with default `wheel-tag = "auto"`, then the built `.whl` filename ends with `-py3-none-<platform>.whl` and `WHEEL` metadata contains `Root-Is-Purelib: false`; given a wheel with `emit = "python-extension"`, `"auto"` sets `infer_tag = True` producing `-cp3XX-cp3XX-<platform>.whl`.
- **Scenario 2 (`wheel-tag = "py3-none"` on extension wheel)**: Given a `python-extension` wheel with `wheel-tag = "py3-none"`, when `uv build --wheel` runs, then the built wheel is named `<dist>-<ver>-py3-none-<platform>.whl` with `my_pkg/_core.so` and `Root-Is-Purelib: false`.
- **Scenario 3 (PEP 639 self-build)**: Given `hatch-mojo`'s own `pyproject.toml` and `LICENSE`, when `uv build` runs, then Hatchling builds both sdist and wheel cleanly without deprecation warnings and embeds `License-Expression: MIT` and `licenses/LICENSE` inside `.dist-info`.

### 2.5 Alternatives Considered
- **Hardcoding `sysconfig.get_platform()` for `py3-none` platform tags**: Rejected because `sysconfig.get_platform()` formats hyphens/dots (`linux-x86_64`, `macosx-14.2-arm64`) incompatibly with PEP 425 wheel filenames and ignores Hatchling's `macos-max-compat` / `MACOSX_DEPLOYMENT_TARGET` normalization, whereas `packaging.tags.sys_tags()` + `process_macos_plat_tag` matches `WheelBuilder.get_best_matching_tag()` identically.

## 3. Requirement-to-Task Traceability Matrix

| Requirement | Owning Task(s) | Verification Strategy | Confirmed Public Seam & Canonical Test Surface |
| --- | --- | --- | --- |
| R1 | `t01` | `behavior_tdd` | `tests/test_config.py`, `tests/test_artifacts.py`, `tests/test_plugin.py`, `tests/test_integration_wheel.py` |
| R2 | `t02` | `static_validation` | `LICENSE`, `pyproject.toml`, `Makefile`, `.github/workflows/{ci,publish}.yml`, `tests/test_integration_wheel.py` (`uv build`) |
| R3 | `t03` | `documentation_validation` | `README.md`, `.agents/skills/{hatch-build-pipeline,native-runtime-bundling,review-*}/**` |

## 4. Implementation Plan

### Phase 1: Wheel Tag Policy, PEP 639 Packaging, CI & Documentation
- [x] [6d73892] t01 — Implement `wheel-tag` (`auto`/`infer`/`py3-none`/custom) config validation and `register_artifacts` platform tag resolution (tasks/t01-wheel-tag-policy.md)
- [x] [5b79a13] t02 — Migrate `pyproject.toml` to PEP 639 with MIT `LICENSE`, clean `Makefile`, and add `macos-latest` + Python `3.15` CI (tasks/t02-pep639-metadata-and-ci-matrix.md)
- [x] [19d20d7] t03 — Rewrite `README.md` for Mojo `1.2+` / `cibuildwheel 4.x` and synchronize `.agents/skills/` invariants (tasks/t03-docs-and-skill-alignment.md)
- **Phase 1 Recovery Checkpoint**: `uv build && uv run ruff check . && uv run ruff format --check . && uv run mypy && uv run pyright && uv run slotscheck hatch_mojo && uv run pytest -q`

## 5. Continuity Snapshot
- **Flow ID**: `wheel-tags-metadata-and-ci` (`state: completed`, `plan_revision: 3`, `plan_commit: 7e10d5b`)
- **Current Task**: `null`
- **Last Verified Checkpoint**: `19d20d7`
- **Key Decisions**:
  - `wheel-tag` defaults to `"auto"` (`"infer"` when any `python-extension` job is present; `"py3-none"` when native jobs are exclusively standalone `executable`/`shared-lib`), with explicit `"py3-none"` and custom PEP 425 tag overrides.
  - `trove_classifiers` in `uv.lock` already includes `"Programming Language :: Python :: 3.15"`, allowing immediate PEP 639 + Python 3.15 metadata verification via `uv build`.
- **Recent Discoveries**:
  - `hatchling.builders.wheel.WheelBuilder.build_standard` checks `if "tag" not in build_data:` before `if build_data["infer_tag"]:`, so setting `build_data["tag"] = f"py3-none-{plat}"` alongside `infer_tag = False` and `pure_python = False` integrates directly with `WheelBuilder.write_archive_metadata`.
  - Achieved `100.00%` statement and branch coverage (`179 passed`, `covdefaults` `fail-under = 100`) in `7a96a66` and synchronized all 14 documentation, skill, and OKF knowledge files in `19d20d7`.
