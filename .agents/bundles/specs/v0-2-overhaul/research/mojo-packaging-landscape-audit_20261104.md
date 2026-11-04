---
type: Research
research_id: "mojo-packaging-landscape-audit-20261104"
title: "Primary-Source Audit: November 2026 Mojo Packaging Landscape and hatch-mojo Strategy"
description: "Audit of Mojo 0.26.2–1.2.0, Python wheel build backends, Hatchling 1.26–1.33, and hatch-mojo v0.1.8 defects recommending a targeted v0.2.0 overhaul."
scope: architecture
status: stable
state: promoted
promoted_to: v0-2-overhaul
tags: [mojo, packaging, hatchling, wheels, roadmap]
generated:
  by: flow/0.26.0
  at: 2026-11-04T04:32:00Z
verified:
  - by: agent:researcher
    at: 2026-11-04T04:32:00Z
    commit: 9782b0b
sources:
  - id: mojo-releases
    resource: https://mojolang.org/releases/
    title: Official Mojo 0.26.2 through 1.2.0 release notes (March–October 2026)
  - id: mojo-cli-build
    resource: https://mojolang.org/docs/cli/build.md
    title: Mojo 1.2.0 CLI build and --emit reference
  - id: mojo-cli-precompile
    resource: https://mojolang.org/docs/cli/precompile.md
    title: Mojo 1.2.0 CLI precompile (.mojoc) reference
  - id: mojo-from-python
    resource: https://mojolang.org/docs/manual/python/mojo-from-python.md
    title: Calling Mojo from Python (PythonModuleBuilder and mojo.importer)
  - id: mojo-oss-license
    resource: https://www.modular.com/blog/mojo-open-source
    title: Mojo compiler, stdlib, and runtime open-source Apache-2.0 WITH LLVM-exception announcement
  - id: max-license
    resource: https://www.modular.com/legal/max-license
    title: MAX License (Modular 26.7, Section 1.5 Apache-2.0 precedence)
  - id: pypi-mojo-compiler
    resource: https://pypi.org/pypi/mojo-compiler/json
    title: PyPI mojo-compiler 1.2.0 wheel metadata and platform tags
  - id: pypi-mogemma
    resource: https://pypi.org/pypi/mogemma/json
    title: PyPI mogemma 0.5.0 production Mojo wheel distribution metadata
  - id: mohaus-repo
    resource: https://github.com/aarnphm/mohaus
    title: Community Rust/Mojo PEP 517 build backend (mohaus)
  - id: pixi-build-mojo
    resource: https://prefix-dev.github.io/pixi-build-backends/backends/pixi-build-mojo/
    title: Pixi Conda build backend for native Mojo packages
  - id: hatchling-history
    resource: https://hatch.pypa.io/latest/history/hatchling/
    title: Hatchling 1.26.0–1.33.0 changelog and BuildHookInterface lifecycle
  - id: cibuildwheel-changelog
    resource: https://cibuildwheel.pypa.io/en/stable/changelog/
    title: cibuildwheel 3.0.0–4.3.5 changelog
  - id: sut-compiler
    resource: hatch_mojo/compiler.py::build_command
    title: Current Mojo compiler discovery and CLI invocation
  - id: sut-runtime
    resource: hatch_mojo/runtime.py::bundle_runtime_libs
    title: Current Modular SDK discovery, runtime bundling, and license notice
  - id: sut-plugin
    resource: hatch_mojo/plugin.py::MojoBuildHook
    title: Current Hatchling build hook lifecycle and editable copy-back
  - id: sut-planner
    resource: hatch_mojo/planner.py::_default_output
    title: Current job glob expansion, output path resolution, and DAG planning
  - id: sut-artifacts
    resource: hatch_mojo/artifacts.py::register_artifacts
    title: Current Hatch build_data force_include, scripts/data, and tag registration
---

# November 2026 Mojo Packaging Landscape & `hatch-mojo` Strategy

<!-- truth: start -->
- Between `hatch-mojo v0.1.8` (`2026-03-07`, Mojo `0.26.1`) and `2026-11-04`, Mojo shipped seven releases culminating in **Mojo `1.2.0` / MAX `26.7.0`** (`2026-10-22`), open-sourced the compiler and runtime under **`Apache-2.0 WITH LLVM-exception`**, and was acquired by Qualcomm[^mojo-releases][^mojo-oss-license][^max-license].
- Modular provides **no official PEP 517 Python wheel backend** in November 2026; native Mojo packaging targets Conda (`rattler-build` + `mojo precompile` `.mojoc` + `pixi-build-mojo`), leaving `hatch-mojo` as the sole PyPI-published Mojo wheel plugin with self-contained `<pkg>.libs/` runtime bundling[^mojo-cli-precompile][^mojo-from-python][^pixi-build-mojo].
- Mojo `1.2.0` extensions still dynamically link `libKGENCompilerRTShared.{so,dylib}` (no static runtime linking and no lightweight `mojo-runtime` PyPI wheel), confirming `<pkg>.libs/` RPATH bundling as the sound default strategy[^mojo-cli-build][^pypi-mojo-compiler][^pypi-mogemma].
- Mojo `1.2.0` `std.python` dynamically resolves `libpython` symbols at runtime via `dlopen`/`dlsym` across CPython `3.10`–`3.14`, enabling single-binary `py3-none-<platform>` wheels on Linux (`manylinux_2_34_{x86_64,aarch64}`) and macOS (`macosx_13_0_arm64`)[^mojo-from-python][^pypi-mojo-compiler].
- `hatch-mojo v0.1.8` has Mojo `1.2.0` breakages (`--emit executable`/`static-lib`, legacy `modular` discovery, retired `Modular Community License` notice) plus internal Hatchling lifecycle bugs (`clean-after-build` in `initialize()`, broken editable RPATHs, hardcoded `build/mojo`, misrouted `scripts`/`data`)[^sut-compiler][^sut-runtime][^sut-plugin][^sut-planner][^sut-artifacts].
- **Recommended Decision**: Execute a **Targeted Architectural Overhaul (`v0.2.0`)** preserving the Hatchling `BuildHookInterface` plugin model while modernizing Mojo `1.2+`, Hatchling `1.33+`, editable, caching, and wheel-tag seams.
<!-- truth: end -->

## 1. Upstream Changes Since `v0.1.8` (`2026-03-07` &rarr; `2026-11-04`)

### 1.1 Mojo `0.26.2` &rarr; `1.2.0` & MAX `26.2` &rarr; `26.7`
- **Release Train & SemVer Split**: Mojo decoupled from `26.x` versioning at `1.0.0b1` (`2026-05-07`), reached **`1.0.0` GA** (`2026-08-11`), open-sourced the compiler/runtime (`2026-08-18`), shipped **`1.1.0`** (`2026-09-17`), and reached **`1.2.0`** (`2026-10-22`, paired with `max==26.7.0`; nightlies at `1.3.0.dev*`). Qualcomm completed its acquisition of Modular on `2026-07-29` (*Modular Inc, a Qualcomm Company*)[^mojo-releases][^max-license].
- **Compiler CLI Hard Changes**:
  - Emoji extensions (`.🔥`, `📦`) were removed in `0.26.2`; `mojo package` became `mojo precompile` (emitting `.mojoc` IR archives) in `1.0.0b2`; `.mojopkg` was removed completely in `1.1.0`[^mojo-releases][^mojo-cli-precompile].
  - In `1.2.0`, `mojo build --emit` strictly validates output types against the target: **`exe`** (default), **`shared-lib`**, **`object`**, **`asm`**, **`llvm`**, **`llvm-bitcode`**, and **`air`**. Neither `executable` nor `static-lib` is a valid `--emit` value[^mojo-cli-build].
  - `-I` gained PEP 420-style namespace merging across directories (`1.1.0`); `-DKEY=VAL`, `--lld-path`, `--fp-mode`, and `mojo --print-cache-location` / `--clear-cache` were added[^mojo-releases][^mojo-cli-build].
- **Python Interop (`std.python.bindings`)**:
  - Source syntax broke across `1.0.0b2`–`1.1.0`: `fn` was removed (`def` only), `std.` imports are mandatory (`from std.python.bindings import PythonModuleBuilder`), and entry points require `@export def PyInit_<mod>() abi("C") -> PythonObject:` (cannot raise across `abi("C")`)[^mojo-releases][^mojo-from-python].
  - `std.python` resolves CPython C-API symbols dynamically via `dlopen`/`dlsym` across CPython `3.10`–`3.14` (Python `3.9` dropped). Free-threaded `3.13t`/`3.14t` `libpython` lookup works (`#6366`), but `PythonModuleBuilder` omits `Py_MOD_GIL_NOT_USED`, so CPython re-enables the GIL on import[^mojo-releases][^mojo-from-python].
  - Shared libraries calling `parallelize()` without a Mojo `main()` must invoke `std.runtime.initialize_runtime()`[^mojo-cli-build].
- **PyPI Packages, Platforms, & Licensing**:
  - Modular deprecated the `modular` metapackage in favor of `mojo==1.2.0` (full dev suite) and **`mojo-compiler==1.2.0`** (~73–82 MB `py3-none-{macosx_13_0_arm64,manylinux_2_34_aarch64,manylinux_2_34_x86_64}` + `mojo-compiler-mojo-libs==1.2.0`), with `max==26.7.0` housing GPU/layout runtime APIs[^pypi-mojo-compiler].
  - Supported targets remain Linux (`x86_64` with `x86-64-v3` AVX2+, `aarch64`, `glibc >= 2.34`) and macOS Apple Silicon (`arm64`, macOS 13+ wheel tag / macOS 15+ docs). Intel macOS and native Windows (`win32`) remain unsupported[^pypi-mojo-compiler].
  - Mojo's compiler, stdlib, and runtime (`libKGENCompilerRTShared`, etc.) are licensed under **`Apache-2.0 WITH LLVM-exception`**[^mojo-oss-license]. Modular `26.7` replaced the *Modular Community License* with the **`MAX License`**, whose Section 1.5 explicitly affirms that `Apache-2.0 WITH LLVM-exception` governs Mojo components[^max-license].

### 1.2 November 2026 Packaging Ecosystem & Upstream Python Tooling
- **Native Mojo vs. Python Wheels**: Modular standardized native Mojo library distribution on **Pixi + `rattler-build` + `mojo precompile` (`.mojoc`)** to `prefix.dev` (`pixi-build-mojo` remains `0.1.*` preview for `.conda` artifacts)[^mojo-cli-precompile][^pixi-build-mojo]. For Python users, official docs (`Beta`) cover only `mojo.importer` (requires ~80 MB `mojo-compiler` at runtime and cannot pass `-I` include paths) and manual `mojo build --emit shared-lib`[^mojo-from-python].
- **Competing Python Builders**: `hatch-mojo` remains the only Mojo wheel plugin on PyPI. Community project `aarnphm/mohaus` provides a `maturin`-like Rust/Mojo PEP 517 backend (with `src/` + `python/` layout, caching, and `.pyi` stub generation) on a custom GitHub Pages index, but replaces Hatchling and does not bundle `<pkg>.libs/` runtime libraries[^mohaus-repo][^pypi-mogemma].
- **Hatchling `1.33.0` & `cibuildwheel 4.3.5`**:
  - Hatchling `1.26`–`1.33.0` standardized PEP 639 (`license = "MIT"`), added Python `3.15` support (`1.33.0`), fixed `WheelBuilder.add_shared_scripts` (`1.31.0`) to preserve native binary executables verbatim, and broke `BuildHookInterface[Any]` in `1.32.3` (fixed in `1.32.4`)[^hatchling-history].
  - `cibuildwheel` reached `4.3.5`, adding native `manylinux_2_34` images and `build-frontend = "uv"`, dropping preinstalled `wheel` (breaking `python -m wheel tags`), and enabling CPython `3.14`, `3.15`, `cp314t`, and `cp315t` by default[^cibuildwheel-changelog].

## 2. Concrete Defects in `hatch-mojo v0.1.8`

1. **Invalid Mojo 1.2 `--emit` Flags (`compiler.py`)**: `build_command` maps `"executable"` &rarr; `"executable"` (Mojo requires `"exe"`) and exposes `"static-lib"` (unsupported by `mojo build`)[^mojo-cli-build][^sut-compiler].
2. **Stale SDK Discovery (`runtime.py`)**: `discover_modular_lib` checks `find_spec("modular")` and walks 5 parents from `mojo_bin`, missing `mojo` / `mojo-compiler` `mojo._package_root` layouts and external tool-venv console scripts (`<venv>/bin/mojo` &rarr; `<venv>/lib/python3.X/site-packages/modular/lib`)[^pypi-mojo-compiler][^sut-runtime].
3. **Inaccurate License Notice (`runtime.py`)**: `_MOJO_RUNTIME_NOTICE` cites the retired *Modular Community License* instead of `Apache-2.0 WITH LLVM-exception`[^mojo-oss-license][^sut-runtime].
4. **Fatal `clean-after-build` Lifecycle Bug (`plugin.py`)**: `MojoBuildHook.initialize` deletes compiled outputs before `WheelBuilder` archives `force_include`, raising `FileNotFoundError`; post-build cleanup belongs in `MojoBuildHook.finalize`[^hatchling-history][^sut-plugin].
5. **Broken Editable Builds (`plugin.py`, `runtime.py`)**: Editable builds rewrite extension RPATHs to `../<pkg>.libs` without staging `<pkg>.libs` beside source packages or using `build_data["force_include_editable"]`, causing `ImportError` on import[^sut-plugin][^sut-runtime].
6. **Misrouted `scripts`/`data` & Unbundled Binaries (`artifacts.py`, `runtime.py`)**: `install.kind = "scripts"` writes to `site-packages/` via `force_include` instead of `build_data["shared_scripts"]`, and `bundle_runtime_libs` ignores `executable` and `shared-lib` jobs[^hatchling-history][^sut-runtime][^sut-artifacts].
7. **Planner, Config, & Caching Gaps (`planner.py`, `config.py`)**: `_default_output` hardcodes `"build/mojo"` instead of `config.build_dir`; multi-file globs collide on output paths and break `depends-on` names; `fail-fast = false` leaves failed jobs in `planned`; profile list/dict fields overwrite instead of merging; and zero mtime/digest build caching exists[^sut-planner][^sut-plugin].

## 3. Options Matrix & Recommendation

| Strategy | Summary | Verdict | Rationale |
| --- | --- | --- | --- |
| **Retire** | Defer to Modular, `pixi-build-mojo`, or `mohaus` | Reject | Modular has no Python wheel backend; `pixi-build-mojo` builds `.conda` only; `mohaus` is off-PyPI, abandons Hatchling, and lacks `<pkg>.libs/` bundling[^mojo-from-python][^mohaus-repo][^pixi-build-mojo]. |
| **Minor Upgrade (`0.1.9`)** | Patch `--emit exe`, discovery, and license notice only | Reject | Leaves fatal `finalize` lifecycle, editable RPATH, `shared_scripts`, `build-dir`, and `cp3XX` matrix bloat unresolved[^sut-plugin][^sut-artifacts]. |
| **Full Rewrite** | Replace Hatchling hook with standalone Rust/Mojo PEP 517 backend | Reject | Discards Hatchling's PEP 639/versioning/hook ecosystem; Python orchestration overhead is negligible next to `mojo build` (~3.6 GB RAM)[^hatchling-history]. |
| **Targeted Overhaul (`0.2.0`)** | Keep Hatchling hook + 6-module pipeline; overhaul Mojo 1.2, lifecycle, editable, tag, and cache seams | **Adopt** | Aligns with Mojo `1.2+` and Hatchling `1.33+`, unlocks zero-setup `mojo-compiler` PEP 517 builds and 5x smaller CI matrices via `py3-none-<platform>` wheels[^pypi-mojo-compiler][^mojo-from-python]. |

### Recommended `v0.2.0` Overhaul Scope
1. **Mojo `1.2+` Toolchain & Licensing**: Map `executable` &rarr; `--emit exe`, remove/guard `static-lib` (optionally add `precompile` `.mojoc`), resolve SDK via `mojo._package_root` / `mojo-compiler` + wrapper venv site-packages, update `_MOJO_RUNTIME_NOTICE` to `Apache-2.0 WITH LLVM-exception`, and drop leaky `win32` production shims.
2. **Hatchling `1.33+` Lifecycle & Artifacts**: Move `clean-after-build` to `MojoBuildHook.finalize()`, clean staged `<pkg>.libs` directories, honor `config.build_dir` in `planner._default_output`, route `scripts`/`data` to `shared_scripts`/`shared_data` (`hatchling>=1.31.0,!=1.32.3`), and extend runtime bundling to `executable` and `shared-lib` jobs.
3. **First-Class Editable Installs & Incremental Caching**: Use `force_include_editable` and SDK-direct RPATHs (or staged `.libs`) for `version == "editable"`, plus input/include/flag digest caching to skip unchanged `mojo build` invocations.
4. **ABI-Independent Wheel Tagging & CI Modernization**: Add opt-in/auto `py3-none-<platform>` wheel tagging (leveraging Mojo's dynamic `libpython` lookup across CPython `3.10`–`3.14`), adopt PEP 639 `license = "MIT"`, add `macos-latest` (`arm64`) and Python `3.15` CI coverage, and update `cibuildwheel 4.x` recipes.

## Provenance

[^mojo-releases]: `https://mojolang.org/releases/` — Official release notes for Mojo `0.26.2`, `1.0.0b1`, `1.0.0b2`, `1.0.0`, `1.1.0`, and `1.2.0`.
[^mojo-cli-build]: `https://mojolang.org/docs/cli/build.md` — Authoritative `mojo build --emit` values (`exe`, `shared-lib`, `object`, `asm`, `llvm`, `llvm-bitcode`, `air`) and runtime initialization notes.
[^mojo-cli-precompile]: `https://mojolang.org/docs/cli/precompile.md` — `mojo precompile` `.mojoc` package format replacing `mojo package` / `.mojopkg`.
[^mojo-from-python]: `https://mojolang.org/docs/manual/python/mojo-from-python.md` — `std.python.bindings.PythonModuleBuilder`, `@export def PyInit_<mod>() abi("C")`, dynamic `libpython` lookup, and `mojo.importer` constraints.
[^mojo-oss-license]: `https://www.modular.com/blog/mojo-open-source` — Open-sourcing of Mojo compiler, stdlib, and runtime under `Apache-2.0 WITH LLVM-exception`.
[^max-license]: `https://www.modular.com/legal/max-license` — Modular `26.7` MAX License replacing Modular Community License, including Section 1.5 `Apache-2.0 WITH LLVM-exception` precedence.
[^pypi-mojo-compiler]: `https://pypi.org/pypi/mojo-compiler/json` — PyPI metadata for `mojo-compiler==1.2.0` (`manylinux_2_34_*` and `macosx_13_0_arm64` wheels).
[^pypi-mogemma]: `https://pypi.org/pypi/mogemma/json` — Production Mojo Python wheel package using `hatch-mojo` `<pkg>.libs/` bundling.
[^mohaus-repo]: `https://github.com/aarnphm/mohaus` — Community Rust/PyO3 + Mojo PEP 517 build backend.
[^pixi-build-mojo]: `https://prefix-dev.github.io/pixi-build-backends/backends/pixi-build-mojo/` — Pixi Conda build backend for native Mojo packages.
[^hatchling-history]: `https://hatch.pypa.io/latest/history/hatchling/` — Hatchling `1.26.0`–`1.33.0` release history (`shared_scripts`, PEP 639, `1.32.3` regression, Python `3.15`).
[^cibuildwheel-changelog]: `https://cibuildwheel.pypa.io/en/stable/changelog/` — `cibuildwheel` `3.0.0`–`4.3.5` changes (`manylinux_2_34`, `uv` frontend, default `cp314t`/`cp315t`, removed `wheel` preinstall).
[^sut-compiler]: `hatch_mojo/compiler.py::build_command` — Current `--emit` mapping (`executable`, `static-lib`) and `mojo` discovery.
[^sut-runtime]: `hatch_mojo/runtime.py::bundle_runtime_libs` — Current `modular` discovery, `python-extension`-only bundling, and `Modular Community License` notice.
[^sut-plugin]: `hatch_mojo/plugin.py::MojoBuildHook` — Current `initialize()` `clean_after_build` defect and `_copy_editable_artifacts` implementation.
[^sut-planner]: `hatch_mojo/planner.py::_default_output` — Hardcoded `build/mojo` output path and glob/DAG expansion.
[^sut-artifacts]: `hatch_mojo/artifacts.py::register_artifacts` — Current `force_include` routing for `scripts`/`data` and `infer_tag` mutation.
