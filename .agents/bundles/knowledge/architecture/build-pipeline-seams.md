---
type: Architecture
title: Build Pipeline and Seam Boundaries
description: Six-stage pipeline from Hatchling hook invocation through Mojo compilation, runtime library bundling, and wheel build_data registration.
status: stable
tags: [architecture, pipeline, seams]
generated:
  by: flow/0.26.0
  at: 2026-11-04T03:55:00Z
verified:
  - by: agent:flow-setup
    at: 2026-11-04T03:55:00Z
    commit: 1b6d139
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
    title: Mojo binary discovery, CLI builder, and subprocess runner
  - id: runtime-bundle
    resource: hatch_mojo/runtime.py::bundle_runtime_libs
    title: Dynamic library dependency resolution and ELF/Mach-O patching
  - id: artifacts-reg
    resource: hatch_mojo/artifacts.py::register_artifacts
    title: Hatch build_data force_include, artifacts, and wheel tag mutation
  - id: cleaning-manifest
    resource: hatch_mojo/cleaning.py::clean_from_manifest
    title: Manifest-tracked output deletion
---

# Build Pipeline and Seam Boundaries

<!-- truth: start -->
- `MojoBuildHook` (`hatch_mojo/plugin.py`) is a thin orchestrator over six functional modules (`config`, `planner`, `compiler`, `runtime`, `artifacts`, `cleaning`) connected solely by immutable value objects (`HookConfig`, `JobConfig`, `BuildJob`) and Hatch's `build_data` dictionary[^plugin-init].
- Pipeline stages are strictly unidirectional: lower modules (`config`, `planner`, `compiler`, `runtime`, `artifacts`, `cleaning`) import `hatch_mojo.types` (and `planner` imports `HookConfig`/`JobConfig` from `config`), never `plugin` or `hooks`.
- Classify dependencies into three active tiers: **In-process** (`types`, `config`, `artifacts`), **Local-substitutable** (`planner`, `cleaning` against `tmp_path`, `uv build --wheel` with synthetic `mojo` scripts), and **External boundary** (`mojo`, `ldd`, `otool`, `patchelf`, `install_name_tool`, `codesign` via `subprocess.run`).
<!-- truth: end -->

## Execution Dataflow

```mermaid
flowchart LR
    H["Hatchling Host"] -->|"initialize(version, build_data)"| P["MojoBuildHook (plugin.py)"]
    P --> C["parse_config (config.py)"]
    C -->|"HookConfig"| PL["plan_jobs / plan_jobs_leveled (planner.py)"]
    PL -->|"list[BuildJob]"| CM["discover_mojo + compile_job (compiler.py)"]
    CM -->|"Compiled outputs"| RT["bundle_runtime_libs (runtime.py)"]
    RT -->|"force_include map"| AR["register_artifacts (artifacts.py)"]
    AR -->|"build_data + manifest.json"| CL["save_manifest / clean_from_manifest (cleaning.py)"]
```

## Deep-Module Seam Table

| Module | Public Seam (Interface) | Hidden Implementation | Dependency Category |
| --- | --- | --- | --- |
| `hatch_mojo/hooks.py` & `plugin.py` | `hatch_register_build_hook()`, `MojoBuildHook.initialize(version, build_data)`, `MojoBuildHook.clean(versions)`[^plugin-init] | Editable short-circuiting, `ThreadPoolExecutor` level execution, `_copy_editable_artifacts` across `("", "src", "src/py")` | Host adapter (`BuildHookInterface`) |
| `hatch_mojo/config.py` | `parse_config(raw, *, target_name) -> HookConfig`[^config-parse] | Profile dictionary merging, `include`/`exclude` `fnmatch`, `emit` vs. `module`/`install` cross-field validation, PEP 508 syntax check | In-process (pure) |
| `hatch_mojo/planner.py` | `plan_jobs(root, config)`, `plan_jobs_leveled(root, config)`[^planner-dag] | `sys.platform` / `platform.machine()` / `Marker.evaluate` filtering, input glob expansion (`job[1..N]`), OS suffix selection, Kahn topological sort & cycle detection | Local-substitutable (`tmp_path` filesystem) |
| `hatch_mojo/compiler.py` | `discover_mojo(root, configured)`, `build_command(mojo_bin, root, job)`, `compile_job(...)`[^compiler-exec] | 4-step binary search (`mojo-bin` &rarr; `HATCH_MOJO_BIN` &rarr; `PATH` &rarr; `.venv/bin/mojo`), Darwin `-headerpad_max_install_names`, Windows `.exe`/script fallback | External boundary (`subprocess.run`) |
| `hatch_mojo/runtime.py` | `discover_modular_lib(root, mojo_bin)`, `bundle_runtime_libs(root, build_dir, jobs, mojo_bin)`[^runtime-bundle] | Sentinel lookup (`libKGENCompilerRTShared`), recursive `ldd`/`otool -L` BFS, `<pkg>.libs/` staging, `NOTICE.mojo-runtime`, `patchelf` / `install_name_tool` / `codesign` | External boundary (`subprocess.run` + SDK fs) |
| `hatch_mojo/artifacts.py` | `register_artifacts(*, root, build_data, jobs, target_name)`[^artifacts-reg] | Dotted module destination resolution, `install_kind` routing (`force-include`, `package`, `root`, `data`, `scripts`), `infer_tag=True` & `pure_python=False` | In-process (`build_data` mutation) |
| `hatch_mojo/cleaning.py` | `manifest_path(...)`, `save_manifest(...)`, `clean_from_manifest(...)`[^cleaning-manifest] | JSON serialization of generated artifact paths under `<build_dir>/manifest.json` and idempotent file unlinking | Local-substitutable (`tmp_path` filesystem) |

## Provenance

[^plugin-init]: `hatch_mojo/plugin.py::MojoBuildHook.initialize` — Coordinates build stages and `ThreadPoolExecutor` level execution.
[^config-parse]: `hatch_mojo/config.py::parse_config` — Converts untyped Hatch TOML dicts into frozen `HookConfig` and `JobConfig` instances.
[^planner-dag]: `hatch_mojo/planner.py::plan_jobs` — Expands `JobConfig` entries into topologically ordered `BuildJob` plans.
[^compiler-exec]: `hatch_mojo/compiler.py::compile_job` — Invokes `mojo build` and formats structured execution logs.
[^runtime-bundle]: `hatch_mojo/runtime.py::bundle_runtime_libs` — Stages Modular runtime libraries and patches ELF/Mach-O RPATHs.
[^artifacts-reg]: `hatch_mojo/artifacts.py::register_artifacts` — Populates Hatch `build_data["force_include"]`, `build_data["artifacts"]`, and wheel purity flags.
[^cleaning-manifest]: `hatch_mojo/cleaning.py::clean_from_manifest` — Removes previously emitted outputs listed in `manifest.json`.
