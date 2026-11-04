# Active Specifications

Active Master PRDs and feature specifications (`<flow_id>/spec.md` and `<flow_id>/tasks/<id>-<slug>.md`). Completed specifications are contracted into [../knowledge/index.md](../knowledge/index.md) and recorded in [../log.md](../log.md) upon `/flow:archive`.

## Master PRDs

- [`v0-2-overhaul`](v0-2-overhaul/spec.md) — **hatch-mojo v0.2.0 Architectural Overhaul** (`state: active`, 4 child flows, 15 tasks)

## Ordered Child Flows (`v0-2-overhaul`)

1. [`mojo-1-2-toolchain`](mojo-1-2-toolchain/spec.md) — **Mojo 1.2 Toolchain, Precompile & Apache-2.0 Runtime Discovery** (`state: completed`, 4 tasks: `t01`–`t04`, checkpoint `67252d3`)
2. [`hatchling-lifecycle-and-bundling`](hatchling-lifecycle-and-bundling/spec.md) — **Hatchling 1.33 Lifecycle, Artifact Routing & Full Binary Bundling** (`state: completed`, 4 tasks: `t01`–`t04`, checkpoint `c694718`)
3. [`editable-planner-and-caching`](editable-planner-and-caching/spec.md) — **Editable Installs, Glob/DAG Planner Fixes & Digest Build Cache** (`state: planned`, 4 tasks: `t01`–`t04`, depends on `hatchling-lifecycle-and-bundling`)
4. [`wheel-tags-metadata-and-ci`](wheel-tags-metadata-and-ci/spec.md) — **Wheel Tag Policy, PEP 639 Metadata, Docs & Multi-OS CI** (`state: planned`, 3 tasks: `t01`–`t03`, depends on `editable-planner-and-caching`)
