---
name: hatch-build-pipeline
description: "Use when modifying Hatchling hook registration, pyproject.toml hook configuration parsing, topological job planning, Mojo compiler CLI execution, wheel build_data artifact registration, editable copy-back, or manifest cleanup in hatch_mojo/{hooks,plugin,config,types,planner,compiler,artifacts,cleaning}.py."
---

# Hatch Build Pipeline (`hatch-build-pipeline`)

<!-- truth: start -->
- Preserve the unidirectional pipeline seam: `MojoBuildHook` (`plugin.py`) coordinates `parse_config` &rarr; `plan_jobs` / `plan_jobs_leveled` &rarr; `discover_mojo` + `compile_job` &rarr; `bundle_runtime_libs` &rarr; `register_artifacts` &rarr; `save_manifest` / `clean_from_manifest`.
- Decorate every dataclass in `hatch_mojo/` with `@dataclass(slots=True, frozen=True)` and store sequence fields as `tuple[T, ...]` so `uv run slotscheck hatch_mojo` passes.
- Enforce configuration invariants in `hatch_mojo/config.py::_validate_job`: `emit == "python-extension"` requires `module`; every other `EmitType` requires explicit `install = { kind, path }`.
- Set `build_data["infer_tag"] = True` and `build_data["pure_python"] = False` in `register_artifacts` when `target_name == "wheel"` and any planned job has `emit != "object"`.
- Write PEP 585/604 type annotations (`list[str]`, `T | None`), Google-style docstrings, and zero inline `#` restatement comments.
<!-- truth: end -->

## Scope

Covers `hatch_mojo/hooks.py`, `hatch_mojo/plugin.py`, `hatch_mojo/config.py`, `hatch_mojo/types.py`, `hatch_mojo/planner.py`, `hatch_mojo/compiler.py`, `hatch_mojo/artifacts.py`, `hatch_mojo/cleaning.py`, and their 1:1 test modules under `tests/`.

## Workflow

1. **Inspect Seams & Domain Rules**:
   - Load [`references/architecture-and-patterns.md`](references/architecture-and-patterns.md) when modifying `HookConfig`, `JobConfig`, `BuildJob`, topological planning, compiler flags, or Hatch `build_data` keys.
2. **Design & Implement in Vertical Slices**:
   - Validate untyped Hatch `dict[str, Any]` config inputs strictly inside `hatch_mojo/config.py::parse_config`; pass frozen `HookConfig` and `BuildJob` instances across all downstream modules.
   - Keep `MojoBuildHook.initialize` early-return guards intact (`version == "editable" and config.skip_editable`, inactive `target_name` returning `jobs=()`, empty post-filter `planned` list).
3. **Verify at the Public Seam**:
   - Load [`references/verification.md`](references/verification.md) to write focused public-seam tests in the canonical `tests/test_<module>.py` or `tests/test_integration_*.py` file and run all static and runtime gates.

## Guardrails

- Never import `hatch_mojo.plugin` or `hatch_mojo.hooks` from lower pipeline modules (`config`, `planner`, `compiler`, `runtime`, `artifacts`, `cleaning`).
- Never drop `-Xlinker -headerpad_max_install_names` from `hatch_mojo/compiler.py::build_command` on `darwin` linkable emits (`python-extension`, `shared-lib`, `executable`).
- Never swallow `mojo build` non-zero exit logs; raise `RuntimeError(log)` when `fail_fast=True` or surface via `self.app.display_warning(log)` when `fail_fast=False`.

## Validation

```bash
uv run ruff check . && uv run ruff format --check . && uv run mypy && uv run pyright && uv run slotscheck hatch_mojo
uv run pytest tests/test_config.py tests/test_planner.py tests/test_compiler.py tests/test_artifacts.py tests/test_cleaning.py tests/test_plugin.py tests/test_hooks.py tests/test_integration_compile.py tests/test_integration_wheel.py -q
```

## References

- [Architecture Seams and Implementation Patterns](references/architecture-and-patterns.md)
- [Public-Seam Verification Guide](references/verification.md)
