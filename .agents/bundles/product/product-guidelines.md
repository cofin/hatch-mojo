---
type: Guide
title: Product and Engineering Guidelines
description: Deep-module seam rules, cold-reader documentation standard, typing/slots invariants, and commit conventions.
status: stable
tags: [guidelines, architecture, python]
generated:
  by: flow/0.26.0
  at: 2026-11-04T03:54:00Z
verified:
  - by: agent:flow-setup
    at: 2026-11-04T03:54:00Z
    commit: 1b6d139
sources:
  - id: pyproject-lint
    resource: pyproject.toml
    title: Ruff, Mypy, Pyright, and Slotscheck configuration
  - id: types-mod
    resource: hatch_mojo/types.py::BuildJob
    title: Frozen slotted dataclass convention
  - id: pr-title-ci
    resource: .github/workflows/pr-title.yml
    title: Semantic PR title GitHub Actions gate
---

# Product and Engineering Guidelines

<!-- truth: start -->
- Design deep modules behind narrow functional seams (`parse_config`, `plan_jobs`, `compile_job`, `bundle_runtime_libs`, `register_artifacts`, `clean_from_manifest`); fail fast with actionable `ValueError`, `TypeError`, `FileNotFoundError`, or `RuntimeError` messages including subprocess `stderr`.
- Annotate all Python 3.10+ code with PEP 585 built-in generics (`list`, `dict`, `tuple`, `set`) and PEP 604 unions (`T | None`), passing both strict `mypy` and `pyright`[^pyproject-lint].
- Declare every dataclass in `hatch_mojo/` with `@dataclass(slots=True, frozen=True)` so `uv run slotscheck hatch_mojo` passes with zero errors[^types-mod].
- Never place inline `#` restatement comments in Python code; explain non-obvious platform constraints or invariants inside Google-style docstrings (`# noqa:` and `# type: ignore[...]` directives excepted where tool-required)[^pyproject-lint].
- Write cold-reader-ready, present-tense prose without promotional adjectives, chronological sediment, or workflow ceremony; use Conventional Commit titles (`<type>(<scope>): <summary>`) enforced by CI[^pr-title-ci].
<!-- truth: end -->

## Deep-Module & Seam Tenets

1. **Minimal Magic, Explicit Contracts**: Map `pyproject.toml` inputs deterministically to `mojo build` invocations and Hatch `build_data` entries. Require explicit `module` on `python-extension` jobs and explicit `install = { kind, path }` on non-Python artifacts. Default to clean breaks over undocumented backward-compatibility shims when fixing broken behavior.
2. **One Adapter = Hypothetical Seam; Two Adapters = Real Seam**: Introduce abstraction boundaries only where genuine platform or boundary divergence exists (such as Linux ELF `ldd`/`patchelf` vs. macOS Mach-O `otool`/`install_name_tool`/`codesign`, or Hatchling `BuildHookInterface` vs. pure planning functions).
3. **Fail Loud on External Tooling**: Never swallow subprocess `stderr`. When `mojo`, `ldd`, `otool`, `patchelf`, `install_name_tool`, or `codesign` fails, surface the command and captured `stderr` in the raised exception.

## Prose, Documentation, & PR Discipline

- **Cold-Reader Standard**: Every README section, docstring, ADR, and spec must make sense on the first read to an engineer with zero prior session context. Lead with purpose, public signature or TOML snippet, and concrete invariants.
- **Manifest Coverage**: Read 100% of in-scope source files (`[k/N files documented]`) before authoring documentation or specs, anchoring claims to `path/to/file::Symbol`.
- **Commits & Pull Requests**: Format commit and PR titles as `<type>(<scope>): <summary>` (`feat`, `fix`, `refactor`, `test`, `docs`, `chore`)[^pr-title-ci]. PR bodies contain only `## Summary` and `## Key Changes`.

## Provenance

[^pyproject-lint]: `pyproject.toml` — Configures `ruff` (`select = ["ALL"]`, Google pydocstyle, `target-version = "py310"`), strict `mypy`, `pyright`, and `slotscheck`.
[^types-mod]: `hatch_mojo/types.py::BuildJob` — Canonical frozen, slotted value object passed across pipeline stages.
[^pr-title-ci]: `.github/workflows/pr-title.yml` — Enforces Conventional Commit PR titles via `amannn/action-semantic-pull-request@v5`.
