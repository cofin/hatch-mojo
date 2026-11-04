# Architecture Seams and Implementation Patterns (`hatch-build-pipeline`)

## 1. Configuration Normalization (`hatch_mojo/config.py`)

- `parse_config(raw: dict[str, Any] | None, *, target_name: str) -> HookConfig` is the sole boundary accepting untyped TOML dictionaries.
- Profiles merge left-to-right via `_merge_job_dicts`: `flags` concatenate verbatim (preserving repeated `-Xlinker` pairs), `include-dirs`/`defines`/`depends-on` deduplicate in order, and `env` dicts merge.
- `matches_filters` evaluates git-style `include`/`exclude` globs via `pathspec.GitIgnoreSpec`; literal jobs skipped by filters are recorded in `HookConfig.excluded_jobs` so downstream `depends_on` edges prune cleanly without false `"unknown dependencies"` errors.
- Environment variable overrides: `HATCH_MOJO_SKIP_EDITABLE` (`skip_editable=False` default), `HATCH_MOJO_CACHE` (`cache=True` default), and `HATCH_MOJO_WHEEL_TAG` (`wheel_tag="auto"` default).
- When `target_name` is not in `targets` (default `["wheel"]`), `parse_config` returns a `HookConfig` with `jobs=()` rather than raising `"No build jobs resolved"`.

## 2. DAG Planning & Platform Expansion (`hatch_mojo/planner.py`)

- `_platform_match(job)` evaluates `job.platforms` against `sys.platform`, `job.arch` against `platform.machine().lower()`, and `job.marker` via `packaging.markers.Marker(job.marker).evaluate()`.
- `_expand_inputs(root, pattern)` expands `*?[]` globs and applies `matches_filters` to expanded paths.
- Multi-file globs suffix concrete names as `<name>[1]`, `<name>[2]`, ..., substitute `{stem}` in `module`, `output`, and `install_path`, rewrite downstream `depends_on` references to the expanded job names, and reject colliding `output_path` or install targets.
- `_default_output` stages outputs under `root / config.build_dir` using OS/emit suffixes (`.mojoc` for `mojoc`, `.so`/`.pyd` for `python-extension`, `.so`/`.dylib`/`.dll` for `shared-lib`, `.o`/`.obj` for `object`, `""`/`.exe` for `executable`).
- `_topological_sort` (serial) and `_topological_levels` (parallel `ThreadPoolExecutor` waves) share `_validate_deps` and raise `ValueError` on unknown `depends_on` targets or dependency cycles.

## 3. Compiler Discovery, Invocation & Digest Cache (`hatch_mojo/compiler.py`)

- `discover_mojo(root, configured)` searches in strict priority order:
  1. Explicit `mojo-bin` in `pyproject.toml`
  2. `HATCH_MOJO_BIN` environment variable
  3. `mojo._package_root.get_package_root()` (`mojo-compiler` / `mojo` PyPI wheels)
  4. `shutil.which("mojo")`
  5. `root / ".venv" / "bin" / "mojo"` (or `.venv/Scripts/mojo.{exe,cmd,bat}` on `win32`)
- `build_command` invokes `mojo precompile` for `emit == "mojoc"` (no `--emit`, no Mach-O linker flags) and `mojo build --emit <shared-lib|object|exe>` for native emits, injecting `["-Xlinker", "-headerpad_max_install_names"]` on `sys.platform == "darwin"` for `python-extension`, `shared-lib`, and `executable`.
- On `sys.platform == "win32"`, `compile_job` resolves `.exe`/`.cmd`/`.bat` shims via `_resolve_win32_mojo_bin` and wraps `command` with `sys.executable` only when `_has_shebang(cmd_path)` is `True`.
- `compute_job_digest` and `compile_job(..., use_cache=..., cache_dir=...)` guard `<build_dir>/cache.json` and `<build_dir>/.raw/<digest><suffix>` with a module-level `threading.Lock`, restoring pristine unpatched binaries onto `job.output_path` on cache hits.

## 4. Wheel Registration, Lifecycle & Editable Staging (`hatch_mojo/artifacts.py`, `hatch_mojo/cleaning.py`, `hatch_mojo/plugin.py`)

- `register_artifacts` maps `python-extension` (`_module_dest`), `package`, `root`, and `force-include` into `build_data["force_include"]`, routes `scripts` into `build_data["shared_scripts"]`, and routes `data` into `build_data["shared_data"]`.
- `resolve_host_platform_tag` mirrors Hatchling's `get_best_matching_tag()` (`packaging.tags.sys_tags()` skipping `manylinux`/`musllinux` + `process_macos_plat_tag` on `darwin`) to construct `py3-none-<plat>` tags.
- Zero-Python wheels (`shared_scripts` / `shared_data` / `force_include_editable` without `force_include`) automatically set `target_config.setdefault("bypass-selection", True)`.
- Editable builds (`version == "editable"`) read raw `packages`/`sources` from `build_config.target_config`/`build_config` dicts before fallback `("", "src", "src/py")`, copy dotted package extensions and `install.kind == "package"` outputs into local package directories without polluting `force_include`, route top-level/uncopied `platlib` outputs via `force_include_editable` when `dev-mode-exact` is `True`, run `patch_editable_runtime` on editable destination copies, and track editable artifacts in `editable-manifest.json`.
- `clean_from_manifest` removes tracked manifest files, `cache.json`, and `.raw/`, and prunes empty directories under `build_dir` bottom-up (`include_editable=False` in `MojoBuildHook.finalize`; `include_editable=True` in `MojoBuildHook.clean`).
