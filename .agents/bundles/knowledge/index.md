# Engineering Knowledge Base

Hierarchical OKF v0.2 knowledge chapters for `hatch-mojo`. Read [workflow.md](workflow.md) before executing commands, and load topic chapters matching your task scope.

## Core Workflow

| Title | Type | Description | Tags |
| --- | --- | --- | --- |
| [Project Workflow](workflow.md) | Guide | Canonical build, lint, typecheck, test, and Flow execution rules for `hatch-mojo`. | `workflow`, `commands`, `verification` |

## Subdirectories

| Directory | Scope | Index |
| --- | --- | --- |
| `architecture/` | Deep-module boundaries, pipeline stages, dependency categories, and Hatchling/OS seams | [architecture/index.md](architecture/index.md) |
| `domains/` | Ubiquitous packaging glossary, configuration-to-job lifecycle, and wheel layout invariants | [domains/index.md](domains/index.md) |
| `patterns/` | Slotted frozen dataclasses, strict typing, and idempotent binary-patching wrappers | [patterns/index.md](patterns/index.md) |
| `testing/` | Public-seam TDD rules, 1:1 module-to-test map, boundary mocking, and tight repro commands | [testing/index.md](testing/index.md) |
| `gotchas/` | Mach-O header padding, ARM64 ad-hoc signing, residual RPATHs, permissions, and `build-dir` quirks | [gotchas/index.md](gotchas/index.md) |
| `decisions/` | Architectural Decision Records passing the irreversibility and genuine trade-off filter | [decisions/index.md](decisions/index.md) |
