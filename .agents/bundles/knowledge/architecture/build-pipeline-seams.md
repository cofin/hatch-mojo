---
type: Architecture
title: Build Pipeline and Seam Boundaries
description: Six-stage pipeline from Hatchling hook invocation through Mojo compilation, digest caching, runtime library bundling, and wheel build_data registration.
status: stable
tags: [architecture, pipeline, seams]
generated:
  by: flow/0.26.0
  at: 2026-11-04T03:55:00Z
verified:
  - by: agent:flow-execution
    at: 2026-11-04T20:36:52Z
    commit: 7a96a66
sources:
  - id: plugin-init
    resource: hatch_mojo/plugin.py::MojoBuildHook.initialize
    title: Build hook orchestrator entry point
  - id: config-parse
    resource: hatch_mojo/config.py::parse_config
    title: TOML dictionary parser and schema validator
  - id: planner-dag
    resource: hatch_mojo/planner.py::plan_jobs
    title: Glob expansion, platform filtering, and topological sorting
  - id: compiler-exec
    resource: hatch_mojo/compiler.py::compile_job
    title: Mojo binary discovery, CLI builder, SHA-256 digest cache, and subprocess runner
  - id: runtime-bundle
    resource: hatch_mojo/runtime.py::bundle_runtime_libs
    title: Dynamic library dependency resolution and ELF/Mach-O patching
  - id: artifacts-reg
    resource: hatch_mojo/artifacts.py::register_artifacts
    title: Hatch build_data force_include, shared_scripts/shared_data, and wheel-tag mutation
  - id: cleaning-manifest
    resource: hatch_mojo/cleaning.py::clean_from_manifest
    title: Manifest-tracked output, cache, and empty directory cleanup
---

# Build Pipeline and Seam Boundaries

<!-- truth: start -->
- `MojoBuildHook` (`hatch_mojo/plugin.py`) is a thin orchestrator over six functional modules (`config`, `planner`, `compiler`, `runtime`, `artifacts`, `cleaning`) connected solely by immutable value objects (`HookConfig`, `JobConfig`, `BuildJob`, `RuntimeBundleResult`) and Hatch's `build_data` dictionary[^plugin-init].
- Pipeline stages are strictly unidirectional: lower modules (`config`, `planner`, `compiler`, `runtime`, `artifacts`, `cleaning`) import `hatch_mojo.types` (plus `config` / `artifacts` in `planner` and `compiler` constants in `cleaning`), never `plugin` or `hooks`.
- Classify dependencies into three active tiers: **In-process** (`types`, `config`, `artifacts`), **Local-substitutable** (`planner`, `cleaning`, and `compiler` digest cache against `tmp_path`; `uv build --wheel` and `WheelBuilder` editable builds with synthetic `mojo` scripts), and **External boundary** (`mojo`, `ldd`, `otool`, `patchelf`, `install_name_tool`, `codesign` via `subprocess.run`).
<!-- truth: end -->

## Execution Dataflow

```mermaid
flowchart LR
    H["Hatchling Host"] -->|"initialize / finalize / clean"| P["MojoBuildHook (plugin.py)"]
    P --> C["parse_config (config.py)"]
    C -->|"HookConfig"| PL["plan_jobs / plan_jobs_leveled (planner.py)"]
    PL -->|"list[BuildJob]"| CM["discover_mojo + compile_job + cache.json (compiler.py)"]
    CM -->|"Compiled outputs"| RT["bundle_runtime_libs / patch_editable_runtime (runtime.py)"]
    RT -->|"RuntimeBundleResult"| AR["register_artifacts (artifacts.py)"]
    AR -->|"build_data + manifests"| CL["save_manifest / clean_from_manifest (cleaning.py)"]
```

## Deep-Module Seam Table

| Module | Public Seam (Interface) | Hidden Implementation | Dependency Category |
| --- | --- | --- | --- |
| `hatch_mojo/hooks.py` & `plugin.py` | `hatch_register_build_hook()`, `MojoBuildHook.{initialize,finalize,clean}`[^plugin-init] | `ThreadPoolExecutor` level execution, `fail-fast=false` failure/dependent filtering, `build_config`-aware `_stage_editable_jobs` + `force_include_editable`, `bypass-selection`, `finalize` cleanup | Host adapter (`BuildHookInterface`) |
| `hatch_mojo/config.py` | `parse_config(raw, *, target_name) -> HookConfig`, `matches_filters(...)`[^config-parse] | Deep profile merging (`_merge_job_dicts`), `pathspec.GitIgnoreSpec` filtering, `wheel-tag` PEP 425 validation, env overrides (`HATCH_MOJO_*`), legacy `0.x` rejections | In-process (pure) |
| `hatch_mojo/planner.py` | `plan_jobs(root, config)`, `plan_jobs_leveled(root, config)`[^planner-dag] | `sys.platform` / `platform.machine()` / `Marker.evaluate` filtering, `{stem}` glob templating, `depends_on` DAG expansion, `config.build_dir` propagation, Kahn topological sort | Local-substitutable (`tmp_path` filesystem) |
| `hatch_mojo/compiler.py` | `discover_mojo(root, configured)`, `build_command(...)`, `compute_job_digest(...)`, `compile_job(...)`[^compiler-exec] | `mojo._package_root` + PATH/venv discovery, `mojo precompile` vs `mojo build --emit`, Darwin `-headerpad_max_install_names`, shebang-guarded `win32` stubs, thread-safe `cache.json` + `.raw/` restore | External boundary (`subprocess.run`) |
| `hatch_mojo/runtime.py` | `discover_modular_lib(...)`, `bundle_runtime_libs(...)`, `patch_editable_runtime(...)`[^runtime-bundle] | Compiler-matched SDK lookup, recursive `ldd`/`otool -L` BFS across extensions/executables/shared-libs, `<pkg>.libs/` & `lib/<dist>.libs/` staging, `Apache-2.0 WITH LLVM-exception` `NOTICE.mojo-runtime`, `patchelf` / `install_name_tool` / `codesign` | External boundary (`subprocess.run` + SDK fs) |
| `hatch_mojo/artifacts.py` | `resolve_install_target(job)`, `resolve_host_platform_tag(...)`, `register_artifacts(...)`[^artifacts-reg] | Dotted module & `install_kind` routing (`force_include`, `shared_scripts`, `shared_data`), `wheel-tag` (`auto`/`infer`/`py3-none`/custom) + macOS tag normalization | In-process (`build_data` mutation) |
| `hatch_mojo/cleaning.py` | `manifest_path(...)`, `save_manifest(...)`, `clean_from_manifest(...)`[^cleaning-manifest] | Separate `manifest.json` vs `editable-manifest.json`, `cache.json`/`.raw/` cleanup, and bottom-up empty directory pruning | Local-substitutable (`tmp_path` filesystem) |

## Provenance

[^plugin-init]: `hatch_mojo/plugin.py::MojoBuildHook.initialize` — Coordinates build, editable staging, bundling, and `finalize` cleanup stages.
[^config-parse]: `hatch_mojo/config.py::parse_config` — Converts untyped Hatch TOML dicts into frozen `HookConfig` and `JobConfig` instances.
[^planner-dag]: `hatch_mojo/planner.py::plan_jobs` — Expands `JobConfig` entries into topologically ordered `BuildJob` plans.
[^compiler-exec]: `hatch_mojo/compiler.py::compile_job` — Invokes `mojo build` / `mojo precompile` with SHA-256 `.raw` artifact caching.
[^runtime-bundle]: `hatch_mojo/runtime.py::bundle_runtime_libs` — Stages Mojo runtime libraries and patches ELF/Mach-O RPATHs.
[^artifacts-reg]: `hatch_mojo/artifacts.py::register_artifacts` — Populates Hatch `force_include`, `shared_scripts`, `shared_data`, and wheel tag policy.
[^cleaning-manifest]: `hatch_mojo/cleaning.py::clean_from_manifest` — Removes tracked outputs, cache files, and empty `build_dir` directories.
