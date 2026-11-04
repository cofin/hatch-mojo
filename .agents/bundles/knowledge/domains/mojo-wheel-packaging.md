---
type: Domain
title: Mojo Wheel Packaging Domain
description: Ubiquitous glossary, JobConfig to BuildJob lifecycle, install-kind routing, and pkg.libs wheel bundling invariants.
status: stable
tags: [domain, packaging, wheel]
generated:
  by: flow/0.26.0
  at: 2026-11-04T03:55:00Z
verified:
  - by: agent:flow-setup
    at: 2026-11-04T03:55:00Z
    commit: 1b6d139
sources:
  - id: types-defs
    resource: hatch_mojo/types.py::BuildJob
    title: EmitType, InstallKind, and BuildJob definitions
  - id: config-models
    resource: hatch_mojo/config.py::HookConfig
    title: HookConfig and JobConfig validation invariants
  - id: artifacts-map
    resource: hatch_mojo/artifacts.py::register_artifacts
    title: Wheel force_include, artifacts, and purity tag rules
  - id: runtime-rpath
    resource: hatch_mojo/runtime.py::_compute_extension_rpath
    title: Module-depth RPATH calculation and pkg.libs layout
---

# Mojo Wheel Packaging Domain

<!-- truth: start -->
- Use exact domain type names across specs, code, and tests: `HookConfig`, `JobConfig`, `BuildJob`, `EmitType`, and `InstallKind`[^types-defs][^config-models].
- Every `EmitType == "python-extension"` job requires `module` (dotted import path, e.g., `mogemma._core`) and compiles with `mojo build --emit shared-lib` into `.so` (Linux/macOS) or `.pyd` (Windows)[^config-models].
- Every non-`python-extension` job (`shared-lib`, `static-lib`, `object`, `executable`) requires an explicit `install = { kind, path }` mapping using one of the five `InstallKind` values (`package`, `data`, `scripts`, `root`, `force-include`)[^config-models][^artifacts-map].
- Wheel native tag inference (`infer_tag = True`, `pure_python = False`) triggers when `target_name == "wheel"` and at least one planned job emits a binary other than `"object"`[^artifacts-map].
- Bundled Modular runtime libraries stage under `<build_dir>/<top_pkg>.libs/` and install to wheel root `<top_pkg>.libs/<lib>`, paired with relative RPATHs computed from dotted `module` depth[^runtime-rpath].
<!-- truth: end -->

## Ubiquitous Glossary

| Term | Canonical Symbol | Meaning & Invariant |
| --- | --- | --- |
| **Profile** | `raw["profiles"]` | Named dictionary of reusable job options merged left-to-right before job-specific overrides in `parse_config`[^config-models]. |
| **Job Config** | `hatch_mojo/config.py::JobConfig` | Validated, unexpanded TOML job entry; may still contain glob characters in `input` and un-evaluated platform/marker filters[^config-models]. |
| **Concrete Build Job** | `hatch_mojo/types.py::BuildJob` | Platform-matched, single-file compilation unit produced by `planner._expand_all_jobs`. Multi-file globs expand to `<name>[1]`, `<name>[2]`, etc., rejecting duplicate names[^types-defs]. |
| **Emit Type** | `hatch_mojo/types.py::EmitType` | One of `"python-extension"`, `"shared-lib"`, `"static-lib"`, `"object"`, `"executable"`. Defaults to `"shared-lib"` in `_validate_job` if omitted[^types-defs][^config-models]. |
| **Install Kind** | `hatch_mojo/types.py::InstallKind` | Destination rule for non-extension outputs: `force-include` (exact wheel path), `package` (`<path>/<name>`), `root` (`<name>`), or `data` / `scripts` (appends to `build_data["artifacts"]` + `force_include`)[^artifacts-map]. |
| **Sentinel Library** | `hatch_mojo/runtime.py::_sentinel` | `libKGENCompilerRTShared.so` (Linux) or `libKGENCompilerRTShared.dylib` (macOS), used both to verify candidate `modular/lib` directories and as a guaranteed root runtime dependency. |
| **Module Depth RPATH** | `hatch_mojo/runtime.py::_compute_extension_rpath` | Number of `".."` segments (`len(module.split(".")) - 1`) needed for an extension (`pkg.sub._core` &rarr; depth `2`) to reach sibling `<pkg>.libs/` via `$ORIGIN` or `@loader_path`[^runtime-rpath]. |
| **Editable Copy-Back** | `hatch_mojo/plugin.py::_copy_editable_artifacts` | When `version == "editable"` and `skip-editable = false`, copies built extensions into the first matching source layout (`""`, `"src"`, `"src/py"`) containing `__init__.py` or `__init__.mojo`. |

## Entity Lifecycle

1. **Raw TOML (`dict[str, Any]`)** &rarr; `parse_config` merges `profiles`, applies `include`/`exclude` globs, checks `target_name in targets` (returning `jobs=()` when inactive), and emits `HookConfig`[^config-models].
2. **`HookConfig`** &rarr; `plan_jobs` / `plan_jobs_leveled` filters by `_platform_match`, expands input globs, assigns platform suffixes (`.so`/`.dylib`/`.pyd`/`.dll`/`.a`/`.lib`/`.o`/`.obj`/`.exe`), and topologically orders `BuildJob` instances.
3. **`list[BuildJob]`** &rarr; `compile_job` invokes `mojo build`, `bundle_runtime_libs` populates `<pkg>.libs/` entries, `register_artifacts` mutates Hatch `build_data`[^artifacts-map], and `save_manifest` persists output paths to `<build_dir>/manifest.json`.

## Provenance

[^types-defs]: `hatch_mojo/types.py::BuildJob` — Defines `EmitType`, `InstallKind`, `EMIT_VALUES`, and `BuildJob`.
[^config-models]: `hatch_mojo/config.py::HookConfig` — Validates `profiles`, `jobs`, `emit`, `module`, `install`, and `targets`.
[^artifacts-map]: `hatch_mojo/artifacts.py::register_artifacts` — Maps `BuildJob` outputs into Hatch `force_include`, `artifacts`, `infer_tag`, and `pure_python`.
[^runtime-rpath]: `hatch_mojo/runtime.py::_compute_extension_rpath` — Computes `$ORIGIN` and `@loader_path` relative paths from dotted module depth to `<pkg>.libs`.
