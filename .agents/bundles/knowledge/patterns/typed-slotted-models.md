---
type: Pattern
title: Typed Slotted Value Models
description: Frozen slotted dataclasses, tuple sequence fields, and strict dual-typechecker conventions across hatch_mojo.
status: stable
tags: [pattern, typing, dataclasses]
generated:
  by: flow/0.26.0
  at: 2026-11-04T03:56:00Z
verified:
  - by: agent:flow-setup
    at: 2026-11-04T03:56:00Z
    commit: 1b6d139
sources:
  - id: buildjob-dc
    resource: hatch_mojo/types.py::BuildJob
    title: Frozen slotted BuildJob dataclass with tuple sequence fields
  - id: config-coercion
    resource: hatch_mojo/config.py::_validate_job
    title: TOML coercion helpers (_as_list, _bool) normalizing into frozen dataclasses
  - id: slotscheck-cfg
    resource: pyproject.toml
    title: Slotscheck, Mypy strict, Pyright, and Ruff configuration
---

# Typed Slotted Value Models

<!-- truth: start -->
- Decorate every value class in `hatch_mojo/` with `@dataclass(slots=True, frozen=True)` so `uv run slotscheck hatch_mojo` passes (`MojoBuildHook` inherits `BuildHookInterface` from Hatchling and is exempt via `strict-imports = false`)[^buildjob-dc][^slotscheck-cfg].
- Store collection fields on `HookConfig`, `JobConfig`, and `BuildJob` as `tuple[T, ...]` rather than mutable `list[T]` (`env: dict[str, str]` is copied per job at parse and compile boundaries)[^buildjob-dc][^config-coercion].
- Normalize untyped TOML inputs (`dict[str, Any]`) once at the `hatch_mojo/config.py::parse_config` boundary using `_as_list` and `_bool`, accepting both kebab-case (`include-dirs`, `depends-on`, `extra-args`) and snake_case (`include_dirs`, `depends_on`, `extra_args`) keys where supported[^config-coercion].
- Use PEP 585 built-in generics and PEP 604 `X | None` unions; document non-obvious rationale inside Google-style docstrings rather than inline `#` comments[^slotscheck-cfg].
<!-- truth: end -->

## Canonical Pattern

```python
@dataclass(slots=True, frozen=True)
class BuildJob:
    """A concrete, expanded build job."""

    name: str
    input_path: Path
    output_path: Path
    emit: EmitType
    module: str | None
    install_kind: InstallKind | None
    install_path: str | None
    include_dirs: tuple[str, ...]
    defines: tuple[str, ...]
    flags: tuple[str, ...]
    env: dict[str, str]
    depends_on: tuple[str, ...]
```

Reason: `slotscheck` scans all classes in `hatch_mojo/` on every lint and CI run, and immutable `tuple` attributes prevent accidental cross-job state mutation during `ThreadPoolExecutor` parallel compilation[^buildjob-dc][^slotscheck-cfg].

## Anti-Patterns to Reject

- Plain `@dataclass` without `slots=True, frozen=True` in `hatch_mojo/` (fails `uv run slotscheck hatch_mojo`).
- Passing raw `dict[str, Any]` Hatch config dictionaries into `planner.py`, `compiler.py`, `runtime.py`, or `artifacts.py` instead of typed `HookConfig` / `BuildJob` objects.
- Inline `#` restatement comments in Python bodies.

## Provenance

[^buildjob-dc]: `hatch_mojo/types.py::BuildJob` — Canonical slotted, frozen job specification.
[^config-coercion]: `hatch_mojo/config.py::_validate_job` — Coerces raw TOML values into `JobConfig` tuples and validated `Literal` types.
[^slotscheck-cfg]: `pyproject.toml` — Configures `[tool.slotscheck]`, `[tool.mypy]`, `[tool.pyright]`, and `[tool.ruff]`.
