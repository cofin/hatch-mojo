# hatch-mojo

A [Hatch](https://hatch.pypa.io/) build hook plugin that compiles [Mojo `1.2+`](https://docs.modular.com/mojo/) sources into Python extension modules, shared libraries, CLI executables, object files, and precompiled `.mojoc` packages during PEP 517 wheel and editable builds.

## Installation

```bash
uv add --dev hatch-mojo
```

## Quickstart

### Zero-install isolated PEP 517 build (`mojo-compiler` on PyPI)

Include `mojo-compiler>=1.2.0` in `[build-system].requires` so `uv build`, `uv sync`, and `pip install` provision the Mojo compiler automatically inside isolated build environments:

```toml
[project]
name = "my-pkg"
version = "0.1.0"
requires-python = ">=3.10"

[build-system]
build-backend = "hatchling.build"
requires = ["hatchling>=1.31.0,!=1.32.3", "hatch-mojo", "mojo-compiler>=1.2.0"]

[tool.hatch.build.targets.wheel.hooks.mojo]
targets = ["wheel"]

[[tool.hatch.build.targets.wheel.hooks.mojo.jobs]]
name = "core"
input = "src/mo/my_pkg/core.mojo"
emit = "python-extension"
module = "my_pkg._core"
include-dirs = ["src/mo"]
```

If you manage Mojo via Pixi, Conda, or a local SDK instead of PyPI, omit `mojo-compiler>=1.2.0` from `requires` and `hatch-mojo` will discover `mojo` from `mojo-bin`, `HATCH_MOJO_BIN`, `PATH`, or `.venv`.

Write your Mojo `1.2+` Python extension using `std.python.bindings`:

```mojo
from std.python import PythonObject
from std.python.bindings import PythonModuleBuilder


@export
def PyInit__core() abi("C") -> PythonObject:
    try:
        var m = PythonModuleBuilder("_core")
        m.def_function[add]("add", docstring="Add two integers.")
        return m.finalize()
    except e:
        abort(String("failed to create Python module: ", e))


def add(a: PythonObject, b: PythonObject) raises -> PythonObject:
    return PythonObject(Int(py=a) + Int(py=b))
```

Build a wheel or sync an editable environment:

```bash
uv build --wheel
uv sync
```

## Configuration

Configure the hook under `[tool.hatch.build.targets.wheel.hooks.mojo]` (or `[tool.hatch.build.hooks.mojo]`) in `pyproject.toml`.

### Global options

```toml
[tool.hatch.build.targets.wheel.hooks.mojo]
mojo-bin = "/opt/mojo/bin/mojo"     # explicit compiler binary path
parallel = true                      # compile independent DAG levels concurrently
fail-fast = true                     # raise on first compile failure; if false, omit failed jobs & dependents
cache = true                         # SHA-256 content-digest build cache in <build-dir>/cache.json
wheel-tag = "auto"                   # "auto" | "infer" | "py3-none" | "<py>-<abi>-<plat>"
bundle-libs = true                   # bundle Mojo runtime libraries & rewrite ELF/Mach-O RPATHs
skip-editable = false                # compile & link editable installs by default
clean-before-build = false           # remove tracked artifacts & cache before compiling
clean-after-build = false            # remove standard wheel staging artifacts during Hatch finalize
build-dir = "build/mojo"             # staging & cache directory
targets = ["wheel"]                  # active Hatch build targets
include = ["src/mo/**/*.mojo"]       # git-style pathspec include globs
exclude = ["**/experimental*.mojo"]  # git-style pathspec exclude globs
```

| Environment Variable | Overrides | Accepted Values |
|---|---|---|
| `HATCH_MOJO_BIN` | Default compiler lookup (when `mojo-bin` is unset) | Path or binary name |
| `HATCH_MOJO_CACHE` | `cache` | `1`/`true`/`yes`/`on` or `0`/`false`/`no`/`off` |
| `HATCH_MOJO_SKIP_EDITABLE` | `skip-editable` | `1`/`true`/`yes`/`on` or `0`/`false`/`no`/`off` |
| `HATCH_MOJO_WHEEL_TAG` | `wheel-tag` | `"auto"`, `"infer"`, `"py3-none"`, or `<py>-<abi>-<plat>` |

### Wheel tag policy (`wheel-tag`)

- `"auto"` (default): uses interpreter-specific tags (`cp312-cp312-<platform>`) when any `python-extension` job is present, and `py3-none-<platform>` when native jobs are exclusively standalone `executable` or `shared-lib` binaries. Pure `.mojoc`/`object` wheels remain pure-Python unless overridden.
- `"infer"`: forces Hatchling interpreter/ABI tag inference (`infer_tag = True`).
- `"py3-none"`: emits a single Python-version-independent `py3-none-<platform>` wheel per OS/architecture, leveraging Mojo `1.2+`'s dynamic `libpython` lookup (`dlopen`/`dlsym`) to cut multi-Python CI matrices down to 1 build per platform.
  > **Free-threaded CPython (`cp313t`/`cp314t`) note:** Mojo `1.2.0` extensions do not yet declare `Py_MOD_GIL_NOT_USED`, so importing a `py3-none` Mojo extension on free-threaded Python re-enables the GIL at runtime. Keep `"auto"`/`"infer"` or skip `cp31?t-*` in CI if strict free-threaded isolation is required.
- `"<py>-<abi>-<plat>"`: explicit 3-part PEP 425 tag (for example `"py3-none-manylinux_2_34_x86_64"`).

### Editable installs & incremental build cache

- **Editable installs (`skip-editable = false`)**: `uv sync` and `pip install -e .` compile Mojo sources, copy package extensions (`my_pkg._core`) directly into your local package layout (`packages` / `sources` in `pyproject.toml`, or `src/` / `src/py/`), honor Hatchling `dev-mode-exact` via `force_include_editable`, and patch RPATHs directly to persistent local SDKs without copying 50+ MB of runtime libraries (automatically staging `<build-dir>/editable.libs` when building inside an ephemeral PEP 517 environment).
- **SHA-256 build cache (`cache = true`)**: `hatch-mojo` hashes the compiler binary metadata, job flags/defines/env, entry source, recursive `.mojo`/`.mojoc` imports under the source directory and `include-dirs`, linked flag files, and upstream `depends-on` digests. Pristine unpatched compiler outputs are cached in `<build-dir>/.raw/` so cache hits restore clean binaries before RPATH patching without re-running `mojo`.

### Profiles

Profiles define reusable job settings merged in declaration order before job-level fields (`flags` concatenate verbatim; `include-dirs`, `defines`, and `depends-on` deduplicate in order; `env` dictionaries merge):

```toml
[tool.hatch.build.targets.wheel.hooks.mojo.profiles.release]
include-dirs = ["src/mo"]
defines = [" fast_math=1"]
flags = ["-O3"]
```

### Jobs & `{stem}` multi-file globs

Each job compiles one Mojo input or a glob of inputs. Multi-file globs expand to `<name>[1]`, `<name>[2]`, ..., rewrite downstream `depends-on = ["<name>"]` edges to wait on all expanded jobs, and substitute `{stem}` in `module`, `output`, and `install.path`:

```toml
[[tool.hatch.build.targets.wheel.hooks.mojo.jobs]]
name = "kernels"
profiles = ["release"]
input = "src/mo/kernels/*.mojo"
emit = "python-extension"
module = "my_pkg._{stem}"

[[tool.hatch.build.targets.wheel.hooks.mojo.jobs]]
name = "cli"
input = "src/mo/cli.mojo"
emit = "executable"
depends-on = ["kernels"]
install = { kind = "scripts", path = "my-cli" }

[[tool.hatch.build.targets.wheel.hooks.mojo.jobs]]
name = "sdk_pkg"
input = "src/mo/sdk/lib.mojo"
emit = "mojoc"
install = { kind = "package", path = "my_pkg" }
```

### Job options reference

| Option | Type | Description |
|---|---|---|
| `name` | string | Unique job identifier |
| `input` | string | Path or glob to `.mojo` source(s) |
| `emit` | string | `python-extension`, `shared-lib`, `mojoc` (`mojo precompile`), `object`, `executable` (`--emit exe`) |
| `output` | string | Explicit staging output path (supports `{stem}`) |
| `module` | string | Dotted import path (required for `python-extension`; supports `{stem}`) |
| `install` | object | Required for non-`python-extension` jobs: `{ kind, path }` |
| `profiles` | list | Profile names merged into this job |
| `include-dirs` | list | Directories passed via `-I` |
| `defines` | list | Preprocessor definitions passed via `-D` |
| `flags` | list | Extra CLI arguments passed to `mojo build` / `mojo precompile` |
| `env` | object | Extra environment variables during compilation |
| `platforms` | list | Restrict job to `sys.platform` values (`linux`, `darwin`, `win32`) |
| `arch` | list | Restrict job to `platform.machine()` values (`x86_64`, `arm64`, `aarch64`) |
| `marker` | string | PEP 508 environment marker expression |
| `depends-on` | list | Upstream job names (or glob job names) that must finish first |

### `install.kind` routing (non-extension jobs)

- `package`: installs into `site-packages/<path>/<output.name>`.
- `root`: installs into `site-packages/<output.name>`.
- `force-include`: installs into `site-packages/<path>` (exact file path, or `<path>/<output.name>` when `path` ends with `/`).
- `scripts`: routes via Hatchling `shared_scripts` into `.data/scripts/` (`<prefix>/bin/` on install; exact script name `path = "my-cli"`, or directory prefix when `path` ends with `/`).
- `data`: routes via Hatchling `shared_data` into `.data/data/` (single-segment names like `"share"` or trailing-`/` paths act as directories; multi-segment file paths install verbatim).

Zero-`.py` standalone binary wheels (`scripts` / `data` only) automatically enable Hatchling `bypass-selection`.

## Runtime library bundling

When `bundle-libs = true` (default), `hatch-mojo` walks `ldd` (Linux) / `otool -L` (macOS) across all `python-extension`, `shared-lib`, and `executable` outputs, copies required Mojo SDK libraries (`libKGENCompilerRTShared`, `libAsyncRTMojoBindings`, etc.), and rewrites relative RPATHs:

- **`platlib` artifacts** (`python-extension`, `package`, `root`, `force-include`): stage runtime libraries into `<pkg>.libs/` inside `site-packages` with `$ORIGIN` / `@loader_path` relative RPATHs.
- **`.data/` artifacts** (`scripts`, `data`): stage runtime libraries into `shared_data` (`lib/<dist>.libs/`) with `$ORIGIN/../lib/<dist>.libs` / `@loader_path/../lib/<dist>.libs` RPATHs so standalone CLI tools execute without wrapper scripts.
- **License attribution**: writes `NOTICE.mojo-runtime` under `Apache-2.0 WITH LLVM-exception` (`Copyright (c) Modular Inc, a Qualcomm Company`), appending MAX license notice terms only if proprietary MAX libraries are bundled, and copies any SDK `LICENSE` file as `LICENSE.mojo-runtime`.

### `cibuildwheel` (`4.x`)

Mojo `1.2+` targets `glibc >= 2.34` (`manylinux_2_34`) on Linux and Apple Silicon (`arm64`) on macOS (`macos-latest`). On `cibuildwheel 4.x`, `wheel` is no longer preinstalled in build containers—use `uvx wheel tags` when retagging self-bundled Linux wheels:

```toml
[tool.cibuildwheel]
build-frontend = "uv"
skip = ["cp31?t-*", "pp*", "*-musllinux*"]

[tool.cibuildwheel.linux]
manylinux-x86_64-image = "manylinux_2_34"
manylinux-aarch64-image = "manylinux_2_34"
repair-wheel-command = "uvx wheel tags --remove --platform-tag manylinux_2_34_{platform} {wheel} && mv {wheel} {dest_dir}"

[tool.cibuildwheel.macos]
archs = ["arm64"]
repair-wheel-command = "delocate-wheel -w {dest_dir} {wheel}"
```

> **Tip:** Setting `wheel-tag = "py3-none"` in `[tool.hatch.build.targets.wheel.hooks.mojo]` lets you build once on `"cp312-*"` (`CIBW_BUILD = "cp312-*"`) instead of compiling every Python minor version.
>
> **macOS SIP & `DYLD_LIBRARY_PATH`:** macOS System Integrity Protection strips `DYLD_LIBRARY_PATH` from child shells, so `CIBW_ENVIRONMENT` will not forward it into `repair-wheel-command`. With `bundle-libs = true` (`@rpath` + `@loader_path`), `DYLD_LIBRARY_PATH` is unnecessary; if needed for custom libraries, inline it directly inside `repair-wheel-command`.

## Troubleshooting

| Error | Fix |
|---|---|
| `mojo executable not found` | Add `mojo-compiler>=1.2.0` to `[build-system].requires`, set `mojo-bin` / `HATCH_MOJO_BIN`, or add `mojo` to `PATH` |
| `static-lib` / `.mojopkg` / `.🔥` error | Mojo `1.x` removed `static-lib`, `.mojopkg`, and `.🔥`; use `.mojo` sources and `emit = "mojoc"` (`mojo precompile`) or `"object"` |
| `No build jobs resolved` | Verify `jobs` is non-empty and check `targets`, `include`, and `exclude` |
| `multiple inputs resolve to the same output` | Add `{stem}` to `module`, `output`, or `install.path` on multi-file glob jobs |
| `unknown dependencies` | Ensure `depends-on` references valid job names |

## License

MIT
