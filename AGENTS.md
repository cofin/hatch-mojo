# hatch-mojo Agent Context

Hatch build hook plugin (`hatch_mojo.hooks`) compiling Mojo sources into Python extensions and native wheel artifacts with ELF/Mach-O runtime library bundling.

## Context Map (`.agents/`)

- **Bundle Root (`OKF v0.2`)**: [`.agents/bundles/index.md`](.agents/bundles/index.md)
- **Product & Guidelines**: [`.agents/bundles/product/product.md`](.agents/bundles/product/product.md) | [`.agents/bundles/product/product-guidelines.md`](.agents/bundles/product/product-guidelines.md) | [`.agents/bundles/product/tech-stack.md`](.agents/bundles/product/tech-stack.md)
- **Workflow & Execution Rules**: [`.agents/bundles/knowledge/workflow.md`](.agents/bundles/knowledge/workflow.md)
- **Architecture & Domain Model**: [`.agents/bundles/knowledge/architecture/build-pipeline-seams.md`](.agents/bundles/knowledge/architecture/build-pipeline-seams.md) | [`.agents/bundles/knowledge/domains/mojo-wheel-packaging.md`](.agents/bundles/knowledge/domains/mojo-wheel-packaging.md)
- **Patterns, Testing, Gotchas, & ADRs**: [`.agents/bundles/knowledge/index.md`](.agents/bundles/knowledge/index.md)
- **Active Specifications**: [`.agents/bundles/specs/index.md`](.agents/bundles/specs/index.md)
- **Project-Local Skills & Subagents**: [`.agents/skills/index.md`](.agents/skills/index.md)

## Canonical Commands

```bash
# sync environment (non-destructive)
uv sync --all-extras --dev

# read-only lint, format check, strict mypy, pyright, and slotscheck
uv run ruff check . && uv run ruff format --check . && uv run mypy && uv run pyright && uv run slotscheck hatch_mojo

# auto-fix formatting & lint + type-check + slotscheck
make lint

# focused module test
uv run pytest tests/test_runtime.py -q

# full test suite
uv run pytest

# full verification gate (lint + test + coverage)
make check-all
```

<!-- project-customization: start -->
## Repository Invariants

- Always execute Python commands and tools via `uv run` (`uvx` for standalone tools).
- Target Python `>=3.10` using PEP 585 built-in generics (`list`, `dict`, `tuple`, `set`) and PEP 604 unions (`T | None`).
- Declare every dataclass in `hatch_mojo/` with `@dataclass(slots=True, frozen=True)` so `uv run slotscheck hatch_mojo` passes.
- Never place inline `#` restatement comments in Python code; record rationale inside Google-style docstrings.
- Place tests in the canonical 1:1 test module (`tests/test_<module>.py` or `tests/test_integration_*.py`), exercising public seams without mocking the System Under Test.
- Never create or mutate Git tags, and never push or open PRs without explicit user instruction.
<!-- project-customization: end -->
