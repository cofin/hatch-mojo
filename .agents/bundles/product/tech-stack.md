---
type: Guide
title: Technology Stack
description: Verified Python runtimes, packaging dependencies, static analysis toolchain, and OS binary utilities.
status: stable
tags: [tech-stack, tooling, ci]
generated:
  by: flow/0.26.0
  at: 2026-11-04T03:54:00Z
verified:
  - by: agent:flow-setup
    at: 2026-11-04T03:54:00Z
    commit: 1b6d139
sources:
  - id: pyproject-deps
    resource: pyproject.toml
    title: Runtime dependencies, dependency groups, and tool configurations
  - id: ci-workflow
    resource: .github/workflows/ci.yml
    title: GitHub Actions lint, typecheck, slotscheck, and OS/Python test matrix
  - id: publish-workflow
    resource: .github/workflows/publish.yml
    title: Wheel/sdist build, multi-OS install smoke test, and PyPI trusted publishing
---

# Technology Stack

<!-- truth: start -->
- **Language & Runtime**: Python `>=3.10` (`3.10`, `3.11`, `3.12`, `3.13`, `3.14` tested in CI on `ubuntu-latest` and `windows-latest`; `macos-latest` tested during release install verification)[^pyproject-deps][^ci-workflow][^publish-workflow].
- **Runtime Dependencies**: `hatchling>=1.26.0` (plugin host & `BuildHookInterface`) and `packaging>=24.0` (PEP 508 `Marker` evaluation)[^pyproject-deps].
- **Environment & Build Manager**: `uv` (`uv sync`, `uv run`, `uv build`, `uv lock`) orchestrated via `Makefile` targets[^pyproject-deps].
- **Static Analysis & Testing**: `ruff` (lint + format), `mypy` (`strict = true`), `pyright` (`basic` mode on `hatch_mojo`), `slotscheck` (`hatch_mojo`), and `pytest` with `coverage` / `covdefaults`[^pyproject-deps][^ci-workflow].
- **External Native Binaries (Runtime Boundary)**: `mojo` (`mojo build`), `ldd` + `patchelf` (Linux ELF), and `otool` + `install_name_tool` + `codesign` (macOS Mach-O). Not required to run the unit/integration test suite, which uses synthetic scripts and subprocess boundary mocks.
<!-- truth: end -->

## Dependency & Tool Matrix

| Layer | Package / Binary | Role | Source |
| --- | --- | --- | --- |
| Build Backend & Host | `hatchling>=1.26.0` | Build backend and `[project.entry-points.hatch]` host | `pyproject.toml`[^pyproject-deps] |
| Marker Evaluation | `packaging>=24.0` | Evaluates PEP 508 `marker` expressions and `default_environment()` | `pyproject.toml`[^pyproject-deps] |
| Package & Env Manager | `uv` | Manages `.venv`, dependency groups (`dev`, `lint`, `test`, `docs`, `build`), and wheel builds | `pyproject.toml`[^pyproject-deps] |
| Linting & Formatting | `ruff>=0.7.1` | Enforces `ALL` ruleset (with curated ignores), isort, and 120-column formatting | `pyproject.toml`[^pyproject-deps] |
| Type & Slot Verification | `mypy>=1.13.0`, `pyright>=1.1.386`, `slotscheck>=0.16.5` | Dual static type checking across `hatch_mojo` + `tests` and `__slots__` integrity on `hatch_mojo` | `.github/workflows/ci.yml`[^ci-workflow] |
| Test Suite | `pytest>=8.0.0`, `pytest-cov`, `pytest-mock`, `pytest-xdist`, `pytest-timeout` | Runs unit and wheel-build integration tests (`120s` thread timeout, branch coverage) | `pyproject.toml`[^pyproject-deps] |
| Release & Docs | `bump-my-version`, `sphinx>=8.0.0`, `shibuya`, `myst-parser` | Version bumping (`pyproject.toml`) and documentation toolchain | `pyproject.toml`[^pyproject-deps] |

## Provenance

[^pyproject-deps]: `pyproject.toml` — Defines runtime dependencies, `[dependency-groups]`, and `[tool.*]` settings.
[^ci-workflow]: `.github/workflows/ci.yml` — Runs `ruff`, `mypy`, `pyright`, `slotscheck`, and the `ubuntu-latest` / `windows-latest` Python `3.10–3.14` `pytest` matrix.
[^publish-workflow]: `.github/workflows/publish.yml` — Builds distributions with `uv build`, verifies wheel installation across Linux/Windows/macOS, and publishes to PyPI via OIDC trusted publishing.
