---
type: Guide
title: Project Workflow
description: Canonical build, lint, typecheck, test, and Flow execution rules for hatch-mojo.
status: stable
tags: [workflow, commands, verification]
generated:
  by: flow/0.26.0
  at: 2026-11-04T03:55:00Z
verified:
  - by: agent:flow-setup
    at: 2026-11-04T03:55:00Z
    commit: 1b6d139
sources:
  - id: makefile-gates
    resource: Makefile
    title: Canonical install, lint, type-check, slotscheck, test, coverage, and check-all targets
  - id: ci-gates
    resource: .github/workflows/ci.yml
    title: Non-mutating CI lint, typecheck, slotscheck, and pytest gates
---

# Project Workflow

<!-- truth: start -->
- Task worksheets under `.agents/bundles/specs/<flow_id>/tasks/<id>-<slug>.md` and `spec.md` checklists are the sole authority for task state and commits.
- Always invoke Python tools with `uv run` (`uv run pytest`, `uv run ruff`, `uv run mypy`, `uv run pyright`, `uv run slotscheck hatch_mojo`)[^makefile-gates][^ci-gates].
- Note that `make lint` runs `ruff check --fix --unsafe-fixes` and `ruff format .` (mutating); use `uv run ruff check . && uv run ruff format --check .` for read-only verification[^makefile-gates][^ci-gates].
- Every task worksheet declares one `verification_strategy` (`behavior_tdd`, `regression_tdd`, `characterization`, `static_validation`, `documentation_validation`, `integration_acceptance`).
- Test through confirmed public seams in existing canonical module test files (`tests/test_<module>.py`); never mock the System Under Test, write tautological assertions, or create standalone `test_*remediation*.py` / `test_*audit*.py` files.
- Project-local domain and review skills live under `.agents/skills/` and paired subagents under `.agents/agents/`.
- Never create or mutate Git tags, and never push or open PRs without explicit user instruction.
<!-- truth: end -->

## Canonical Commands

Verified on this Linux host (`Python 3.10.18`, `uv`) against `Makefile`[^makefile-gates] and `.github/workflows/ci.yml`[^ci-gates]:

```bash
# environment sync (non-destructive; avoid `make install` unless recreating .venv from scratch)
uv sync --all-extras --dev

# read-only static verification (lint + format check + strict mypy + pyright + slotscheck)
uv run ruff check . && uv run ruff format --check . && uv run mypy && uv run pyright && uv run slotscheck hatch_mojo

# auto-fix formatting & lint + type-check + slotscheck
make lint

# focused single-module test (tight inner loop)
uv run pytest tests/test_runtime.py -q

# full test suite (unit + wheel build integration)
uv run pytest

# full verification gate (lint + test + coverage report)
make check-all
```

## Direct Markdown Continuity & Execution Loop

1. Resolve `.agents/setup-state.json` (default `.agents/bundles/`), read `index.md`, and inspect active `specs/<flow_id>/spec.md` and `tasks/<id>-<slug>.md`.
2. Run the 5-check preflight (`dependencies_closed`, `worksheet_complete`, `verification_strategy_declared`, `plan_identity_matches`, `target_symbols_exist`) before claiming the ready `pending`/`open` task.
3. Execute one vertical-slice worksheet per isolated `@executor` subagent turn (`model: inherit`), verify exit code `0`, stage only task-owned paths, create one atomic commit, and update task frontmatter (`state: completed`, `commit: <sha>`) and `spec.md` (`- [x] [<sha>] ...`).
4. Run `/flow:learn` at any time to reconcile cross-machine/cross-harness drift, harvest mid-flow discoveries, resynthesize `.agents/bundles/knowledge/**`, and synchronize `.agents/skills/` and `.agents/agents/`.

## Provenance

[^makefile-gates]: `Makefile` — Defines `install`, `lint`, `type-check`, `slotscheck`, `test`, `coverage`, and `check-all` targets.
[^ci-gates]: `.github/workflows/ci.yml` — Executes non-mutating `ruff check`, `ruff format --check`, `mypy`, `pyright`, `slotscheck`, and `pytest` across OS/Python matrices.
