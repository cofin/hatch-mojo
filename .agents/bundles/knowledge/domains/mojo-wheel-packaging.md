---
type: Domain
title: Mojo Wheel Packaging Domain
description: Ubiquitous glossary, JobConfig to BuildJob lifecycle, install-kind routing, wheel-tag policy, and runtime bundling invariants.
status: stable
tags: [domain, packaging, wheel]
generated:
  by: flow/0.26.0
  at: 2026-11-04T03:55:00Z
verified:
  - by: agent:flow-execution
    at: 2026-11-04T20:36:52Z
    commit: 7a96a66
sources:
  - id: types-defs
    resource: hatch_mojo/types.py::BuildJob
    title: EmitType, InstallKind, BuildJob, and RuntimeBundleResult definitions
  - id: config-models
    resource: hatch_mojo/config.py::HookConfig
    title: HookConfig and JobConfig validation invariants
  - id: artifacts-map
    resource: hatch_mojo/artifacts.py::register_artifacts
    title: Wheel force_include, shared_scripts/shared_data, and wheel-tag rules
  - id: runtime-rpath
    resource: hatch_mojo/runtime.py::_compute_relative_rpath
    title: Relative RPATH calculation across platlib and .data layouts
---

# Mojo Wheel Packaging Domain

<!-- truth: start -->
- Use exact domain type names across specs, code, and tests: `HookConfig`, `JobConfig`, `BuildJob`, `RuntimeBundleResult`, `EmitType`, and `InstallKind`[^types-defs][^config-models].
- Every `EmitType == "python-extension"` job requires `module` (dotted import path, e.g., `mogemma._core`), rejects `install`, and compiles with `mojo build --emit shared-lib` into `.so` (Linux/macOS) or `.pyd` (Windows)[^config-models].
- Every non-`python-extension` job (`shared-lib`, `mojoc`, `object`, `executable`) requires an explicit `install = { kind, path }` mapping using one of the five `InstallKind` values (`package`, `data`, `scripts`, `root`, `force-include`)[^config-models][^artifacts-map].
- Wheel native tag policy (`wheel_tag`) triggers `pure_python = False` when `target_name == "wheel"` and at least one planned job has `emit not in {"object", "mojoc"}`, resolving `"auto"` to `"infer"` when `python-extension` jobs exist and `"py3-none"` (`py3-none-<host_plat>`) for standalone native binaries[^artifacts-map].
- Bundled Mojo runtime libraries stage into `<top_pkg>.libs/` (`force_include`) for `platlib` jobs and `lib/<dist>.libs/` (`shared_data`) for `.data/` (`scripts`/`data`) jobs, paired with relative RPATHs computed via `_compute_relative_rpath`[^runtime-rpath].
<!-- truth: end -->

## Ubiquitous Glossary

| Term | Canonical Symbol | Meaning & Invariant |
| --- | --- | --- |
| **Profile** | `raw["profiles"]` | Named dictionary of reusable job options deep-merged left-to-right (`_merge_job_dicts`) before job-specific overrides in `parse_config`[^config-models]. |
| **Job Config** | `hatch_mojo/config.py::JobConfig` | Validated, unexpanded TOML job entry; may contain glob characters in `input`, `{stem}` templates, and un-evaluated platform/marker filters[^config-models]. |
| **Concrete Build Job** | `hatch_mojo/types.py::BuildJob` | Platform-matched, single-file compilation unit produced by `planner._expand_all_jobs`. Multi-file globs expand to `<name>[1..N]`, substitute `{stem}`, and rewrite downstream `depends_on` edges[^types-defs]. |
| **Emit Type** | `hatch_mojo/types.py::EmitType` | One of `"python-extension"`, `"shared-lib"`, `"mojoc"` (`mojo precompile`), `"object"`, `"executable"` (`mojo build --emit exe`). Defaults to `"shared-lib"` if omitted[^types-defs][^config-models]. |
| **Install Kind** | `hatch_mojo/types.py::InstallKind` | Destination rule for non-extension outputs: `force-include`, `package`, `root` (`force_include` `platlib` map), `scripts` (`shared_scripts`), or `data` (`shared_data`)[^artifacts-map]. |
| **Wheel Tag Policy** | `hatch_mojo/config.py::HookConfig.wheel_tag` | `"auto"` (default), `"infer"`, `"py3-none"`, or an explicit 3-part PEP 425 tag (`<py>-<abi>-<plat>`), controlling `infer_tag` and `tag` in `register_artifacts`[^artifacts-map]. |
| **Sentinel Library** | `hatch_mojo/runtime.py::_sentinel` | `libKGENCompilerRTShared.so` (Linux) or `libKGENCompilerRTShared.dylib` (macOS), verifying candidate `modular/lib` directories and seeding runtime dependency walks. |
| **Editable Staging** | `hatch_mojo/plugin.py::_stage_editable_jobs` | Copies dotted package extensions and `package` artifacts into `build_config`-resolved local package dirs, routes top-level/root outputs via `force_include_editable` (`dev-mode-exact`) or `force_include`, and runs `patch_editable_runtime`. |

## Entity Lifecycle

1. **Raw TOML (`dict[str, Any]`)** &rarr; `parse_config` deep-merges `profiles`, evaluates literal `pathspec` filters (recording `excluded_jobs`), validates `wheel-tag` and env overrides, checks `target_name in targets`, and emits `HookConfig`[^config-models].
2. **`HookConfig`** &rarr; `plan_jobs` / `plan_jobs_leveled` filters by `_platform_match`, expands input globs with `{stem}` substitution, assigns `config.build_dir` paths and OS suffixes, rewrites `depends_on`, and topologically orders `BuildJob` instances.
3. **`list[BuildJob]`** &rarr; `compile_job` restores cached `.raw/` outputs or runs `mojo`, `bundle_runtime_libs` / `patch_editable_runtime` links runtime libraries, `register_artifacts` mutates Hatch `build_data`[^artifacts-map], and `save_manifest` persists tracked paths (`manifest.json` / `editable-manifest.json`).

## Provenance

[^types-defs]: `hatch_mojo/types.py::BuildJob` — Defines `EmitType`, `InstallKind`, `EMIT_VALUES`, `BuildJob`, and `RuntimeBundleResult`.
[^config-models]: `hatch_mojo/config.py::HookConfig` — Validates `profiles`, `jobs`, `emit`, `module`, `install`, `wheel_tag`, `cache`, and `targets`.
[^artifacts-map]: `hatch_mojo/artifacts.py::register_artifacts` — Maps `BuildJob` outputs into Hatch `force_include`, `shared_scripts`, `shared_data`, `infer_tag`, `tag`, and `pure_python`.
[^runtime-rpath]: `hatch_mojo/runtime.py::_compute_relative_rpath` — Computes `$ORIGIN` and `@loader_path` relative paths across `platlib` and `.data/` layouts.
