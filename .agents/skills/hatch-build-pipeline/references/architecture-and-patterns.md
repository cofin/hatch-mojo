# Architecture Seams and Implementation Patterns (`hatch-build-pipeline`)

## 1. Configuration Normalization (`hatch_mojo/config.py`)

- `parse_config(raw: dict[str, Any] | None, *, target_name: str) -> HookConfig` is the sole boundary accepting untyped TOML dictionaries.
- Profiles merge in declaration order before job-level keys (`_merge_dict`), followed by `include` and `exclude` `fnmatch` filtering on `job.input`.
- When `target_name` is not in `targets` (default `["wheel"]`), `parse_config` returns a `HookConfig` with `jobs=()` rather than raising `"No build jobs resolved"`. Reason: Hatch invokes registered hooks across targets (`sdist`, `wheel`), and inactive targets must no-op cleanly.
- Support both kebab-case (`include-dirs`, `depends-on`, `extra-args`) and snake_case (`include_dirs`, `depends_on`, `extra_args`) job keys where already established in `_validate_job`.

## 2. DAG Planning & Platform Expansion (`hatch_mojo/planner.py`)

- `_platform_match(job)` evaluates three independent filters: `job.platforms` against `sys.platform`, `job.arch` (lowercased) against `platform.machine().lower()`, and `job.marker` via `packaging.markers.Marker(job.marker).evaluate(environment=default_environment())`.
- `_expand_inputs(root, pattern)` treats `*?[]` as globs (`sorted(path for path in root.glob(pattern) if path.is_file())`) and raises `ValueError` when a glob matches zero files or `FileNotFoundError` when a literal path is missing.
- Multi-file globs suffix concrete names as `<name>[1]`, `<name>[2]`, etc., and reject duplicate concrete job names.
- `_topological_sort` (serial) and `_topological_levels` (parallel `ThreadPoolExecutor` waves) share `_validate_deps` and raise `ValueError` on unknown `depends_on` targets or dependency cycles.
- Note: `_default_output` currently constructs paths under `root / "build/mojo"` directly rather than reading `config.build_dir`. Keep tests and callers aligned if changing custom `build-dir` behavior.

## 3. Compiler Discovery & Invocation (`hatch_mojo/compiler.py`)

- `discover_mojo(root, configured)` searches in strict priority order:
  1. Explicit `mojo-bin` in `pyproject.toml`
  2. `HATCH_MOJO_BIN` environment variable
  3. `shutil.which("mojo")`
  4. `root / ".venv" / "bin" / "mojo"`
- `build_command` maps `emit == "python-extension"` to `--emit shared-lib` and injects `["-Xlinker", "-headerpad_max_install_names"]` on `sys.platform == "darwin"` for `python-extension`, `shared-lib`, and `executable` emits.
- On `sys.platform == "win32"`, `compile_job` checks `<mojo_bin>.exe` first and prefixes `sys.executable` when `command[0]` does not end with `.exe` (enabling Python stub executables in cross-platform CI).

## 4. Wheel Registration & Editable Copy-Back (`hatch_mojo/artifacts.py`, `hatch_mojo/plugin.py`)

- `python-extension` outputs map via `_module_dest(job.module, job.output_path)` (`pkg.sub._core` &rarr; `pkg/sub/_core.so`) into `build_data["force_include"]`.
- Non-extension outputs route by `job.install_kind`:
  - `force-include`: exact `job.install_path`
  - `package`: `<install_path>/<output.name>`
  - `root`: `<output.name>`
  - `data` / `scripts`: appends relative POSIX path to `build_data["artifacts"]` and maps `<install_path>/<output.name>` in `force_include`
- `_copy_editable_artifacts` copies built extensions into the first layout among `("", "src", "src/py")` containing `<pkg>/__init__.py` or `<pkg>/__init__.mojo` when `version == "editable"` and `skip_editable` is `False`.
