---
name: hatch-build-pipeline
description: "Use when modifying Hatchling hook registration, pyproject.toml hook configuration parsing, topological job planning, Mojo compiler CLI execution, wheel build_data artifact registration, editable copy-back, or manifest cleanup in hatch_mojo/{hooks,plugin,config,types,planner,compiler,artifacts,cleaning}.py."
---

# Hatch Build Pipeline (`hatch-build-pipeline`)

<!-- truth: start -->
- Preserve the unidirectional pipeline seam: `MojoBuildHook` (`plugin.py`) coordinates `parse_config` &rarr; `plan_jobs` / `plan_jobs_leveled` &rarr; `discover_mojo` + `compile_job` (with `cache.json` + `.raw/`) &rarr; `bundle_runtime_libs` / `patch_editable_runtime` &rarr; `register_artifacts` &rarr; `save_manifest` (`manifest.json` / `editable-manifest.json`), running `clean_after_build` inside `MojoBuildHook.finalize`.
- Decorate every dataclass in `hatch_mojo/` with `@dataclass(slots=True, frozen=True)` and store sequence fields as `tuple[T, ...]` so `uv run slotscheck hatch_mojo` passes.
- Enforce configuration invariants in `hatch_mojo/config.py::_validate_job`: `emit == "python-extension"` requires `module` and forbids `install`; every other `EmitType` (`shared-lib`, `mojoc`, `object`, `executable`) requires explicit `install = { kind, path }` (non-empty `path` except `kind == "root"`), and legacy `static-lib`, `.🔥`, `📦`, and `.mojopkg` inputs raise `ValueError`.
- Honor `wheel-tag` (`"auto" | "infer" | "py3-none" | "<pep425_tag>"`) in `register_artifacts` when `target_name == "wheel"`: set `pure_python = False` when any planned job has `emit not in {"object", "mojoc"}`, resolving `"auto"` to `"infer"` when `python-extension` jobs exist and `"py3-none"` (`py3-none-<host_plat>`) for standalone native binaries.
- Write PEP 585/604 type annotations (`list[str]`, `T | None`), Google-style docstrings, and zero inline `#` restatement comments.
<!-- truth: end -->

## Scope

Covers `hatch_mojo/hooks.py`, `hatch_mojo/plugin.py`, `hatch_mojo/config.py`, `hatch_mojo/types.py`, `hatch_mojo/planner.py`, `hatch_mojo/compiler.py`, `hatch_mojo/artifacts.py`, `hatch_mojo/cleaning.py`, and their 1:1 test modules under `tests/`.

## Workflow

1. **Inspect Seams & Domain Rules**:
   - Load [`references/architecture-and-patterns.md`](references/architecture-and-patterns.md) when modifying `HookConfig`, `JobConfig`, `BuildJob`, topological planning, compiler flags, caching, editable staging, or Hatch `build_data` keys.
2. **Design & Implement in Vertical Slices**:
   - Validate untyped Hatch `dict[str, Any]` config inputs strictly inside `hatch_mojo/config.py::parse_config`; pass frozen `HookConfig` and `BuildJob` instances across all downstream modules.
   - Keep `MojoBuildHook` lifecycle guards intact (`version == "editable" and config.skip_editable`, inactive `target_name` returning `jobs=()`, `fail-fast = false` failure/dependent filtering, and `finalize` skipping `version == "editable"`).
3. **Verify at the Public Seam**:
   - Load [`references/verification.md`](references/verification.md) to write focused public-seam tests in the canonical `tests/test_<module>.py` or `tests/test_integration_*.py` file and run all static and runtime gates.

## Guardrails

- Never import `hatch_mojo.plugin` or `hatch_mojo.hooks` from lower pipeline modules (`config`, `planner`, `compiler`, `runtime`, `artifacts`, `cleaning`).
- Never drop `-Xlinker -headerpad_max_install_names` from `hatch_mojo/compiler.py::build_command` on `darwin` linkable emits (`python-extension`, `shared-lib`, `executable`), and never pass `--emit` or Mach-O linker flags to `mojo precompile` (`emit == "mojoc"`).
- Never swallow `mojo` non-zero exit logs; raise `RuntimeError(log)` when `fail_fast=True` or filter failed jobs + dependents while surfacing `self.app.display_warning(log)` when `fail_fast=False`.
- Never run `clean_after_build` inside `MojoBuildHook.initialize`; cleanup after wheel archiving belongs exclusively in `MojoBuildHook.finalize` (`include_editable=False`).

## Validation

```bash
uv run ruff check . && uv run ruff format --check . && uv run mypy && uv run pyright && uv run slotscheck hatch_mojo
uv run pytest tests/test_config.py tests/test_planner.py tests/test_compiler.py tests/test_artifacts.py tests/test_cleaning.py tests/test_plugin.py tests/test_hooks.py tests/test_integration_compile.py tests/test_integration_wheel.py -q
```

## References

- [Architecture Seams and Implementation Patterns](references/architecture-and-patterns.md)
- [Public-Seam Verification Guide](references/verification.md)
