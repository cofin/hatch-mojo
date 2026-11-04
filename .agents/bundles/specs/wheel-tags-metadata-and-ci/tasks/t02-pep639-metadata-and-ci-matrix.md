---
type: Task
id: wheel-tags-metadata-and-ci:t02
title: "Migrate pyproject.toml to PEP 639 with MIT LICENSE, clean Makefile, and add macos-latest + Python 3.15 CI"
description: "Add root MIT LICENSE, migrate pyproject.toml to PEP 639 with Python 3.15 classifier, clean Makefile, and expand CI workflows to macOS and Python 3.15."
state: completed
priority: P1
verification_strategy: static_validation
depends_on:
  - wheel-tags-metadata-and-ci:t01
files:
  - LICENSE
  - pyproject.toml
  - Makefile
  - .github/workflows/ci.yml
  - .github/workflows/publish.yml
tests:
  - tests/test_integration_wheel.py
plan_revision: 3
plan_commit: 7e10d5b
state_revision: 2
claimed_by: null
claimed_at: null
blocked_reason: null
unblock_condition: null
next_step: null
last_verified_at: 2026-11-04T20:16:38Z
last_verified_commit: 5b79a13
verification_evidence: "uv lock --check; uv build; uv run pytest -q (169 passed); ruff, mypy, pyright, slotscheck exit 0"
created_at: 2026-11-04T05:12:00Z
updated_at: 2026-11-04T20:17:37Z
commit: 5b79a13
tags: [migration, pep639, makefile, github-actions, ci]
---

# Task `t02`: Migrate `pyproject.toml` to PEP 639 with MIT `LICENSE`, Clean `Makefile`, and Add `macos-latest` + Python `3.15` CI

## Objective

Create the canonical MIT `LICENSE` file, migrate `pyproject.toml` to PEP 639 (`license = "MIT"`, `license-files = ["LICENSE"]`) with Python `3.15` classifier support, clean stale `3.10` / `.hatch_mojo` assumptions in `Makefile`, and expand GitHub Actions workflows to test `macos-latest` and Python `3.15`.

## Context

- **Verification Strategy (`static_validation`)**: Exercises real Hatchling PEP 639 sdist/wheel metadata generation via `uv build`, validates `dist/*.whl` `.dist-info/METADATA` and `.dist-info/licenses/LICENSE` in `tests/test_integration_wheel.py`, and validates YAML workflow schemas and static gates.
- **Confirmed Environment Fact**: `trove_classifiers` in `uv.lock` already includes `"Programming Language :: Python :: 3.15"` and `packaging>=24.2` provides `packaging.licenses.canonicalize_license_expression`, so `uv build` validates PEP 639 offline without network dependencies.

## Steps

1. **Add PEP 639 self-build verification test**:
   - In `tests/test_integration_wheel.py`: add `test_hatch_mojo_self_wheel_pep639_metadata` building the repository root into `tmp_path / "dist"` via `uv build --wheel --out-dir` and asserting the built `hatch_mojo-*.whl` contains `.dist-info/licenses/LICENSE` and `License-Expression: MIT` in `.dist-info/METADATA` without any `License :: OSI Approved ::` classifier.
2. **Update `LICENSE`, `pyproject.toml`, `Makefile`, and GitHub Actions workflows**:
   - Create `LICENSE` at the repository root containing the standard MIT License (`Copyright (c) 2025-present Cody Fincher`).
   - Edit `pyproject.toml`:
     - Replace `license = { text = "MIT" }` with `license = "MIT"` and `license-files = ["LICENSE"]`.
     - Remove `"License :: OSI Approved :: MIT License"` from `classifiers` and append `"Programming Language :: Python :: 3.15"`.
   - Edit `Makefile`:
     - Remove `@uv python pin 3.10 >/dev/null 2>&1` from `install`.
     - Remove `.hatch_mojo` from the `rm -rf` line in `clean`.
   - Edit `.github/workflows/ci.yml`:
     - Update `jobs.test.strategy.matrix.os` to `[ubuntu-latest, macos-latest, windows-latest]`.
     - Update `jobs.test.strategy.matrix.python-version` to `["3.10", "3.11", "3.12", "3.13", "3.14", "3.15"]`.
   - Edit `.github/workflows/publish.yml`:
     - Update `jobs.test-install.strategy.matrix.python-version` to `["3.10", "3.12", "3.13", "3.14", "3.15"]`.
3. **Verify build and static gates**:
   - Run `uv build --out-dir` (into a temporary directory or clean `dist/` afterward), `ruff`, `mypy`, `pyright`, `slotscheck`, and `pytest`.

## Verification

```bash
uv run pytest tests/test_integration_wheel.py -k pep639 -q
uv run ruff check . && uv run ruff format --check . && uv run mypy && uv run pyright && uv run slotscheck hatch_mojo
uv run pytest -q
```

## Acceptance Criteria

- [x] Root `LICENSE` exists with standard MIT text and `pyproject.toml` declares `license = "MIT"`, `license-files = ["LICENSE"]`, and `"Programming Language :: Python :: 3.15"` without `"License :: OSI Approved :: MIT License"` (`R2`).
- [x] `uv build --wheel` embeds `License-Expression: MIT` and `.dist-info/licenses/LICENSE` cleanly (`R2`).
- [x] `Makefile` omits `uv python pin 3.10` and `.hatch_mojo`, `ci.yml` includes `macos-latest` + `"3.15"`, and `publish.yml` includes `"3.14"` + `"3.15"` (`R2`).
- [x] Full static analysis and `pytest` suite exit `0`.

## Notes & Discoveries

_None._
