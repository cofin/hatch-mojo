# hatch-mojo

A [Hatch](https://hatch.pypa.io/) build hook plugin that compiles [Mojo](https://docs.modular.com/mojo/) sources during package builds.

Supports Python extension modules and standalone artifacts (shared libraries, executables, etc.).

## Installation

```bash
uv add hatch-mojo
```

## Quickstart

Add the hook to your `pyproject.toml`:

```toml
[build-system]
build-backend = "hatchling.build"
requires = ["hatchling", "hatch-mojo"]

[tool.hatch.build.targets.wheel.hooks.mojo]
targets = ["wheel"]

[[tool.hatch.build.targets.wheel.hooks.mojo.jobs]]
name = "core"
input = "src/mo/my_pkg/core.mojo"
emit = "python-extension"
module = "my_pkg._core"
include-dirs = ["src/mo"]
```

Then build:

```bash
hatch build -t wheel
```

## Configuration

All configuration lives under `[tool.hatch.build.targets.wheel.hooks.mojo]` in `pyproject.toml`.

### Global options

```toml
[tool.hatch.build.targets.wheel.hooks.mojo]
mojo-bin = "/opt/mojo/bin/mojo"    # path to mojo binary (default: $HATCH_MOJO_BIN or "mojo")
parallel = true                     # compile jobs in parallel
fail-fast = true                    # stop on first failure (only with parallel)
clean-before-build = false          # remove build-dir before compiling
clean-after-build = false           # remove build-dir after compiling
skip-editable = true                # skip Mojo compilation for editable installs
build-dir = "build/mojo"            # working directory for compiled artifacts
targets = ["wheel"]                 # hatch build targets that trigger this hook
include = ["src/mo/**/*.mojo"]      # git-style globs to include
exclude = ["**/experimental*.mojo"] # git-style globs to exclude
```

### Profiles

Profiles define reusable sets of job options. Jobs reference them by name, and profile values are merged into the job config.

```toml
[tool.hatch.build.targets.wheel.hooks.mojo.profiles.default]
include-dirs = ["src/mo"]
flags = ["-I", "vendor/include"]
```

```toml
[[tool.hatch.build.targets.wheel.hooks.mojo.jobs]]
name = "core"
profiles = ["default"]
input = "src/mo/my_pkg/core.mojo"
emit = "python-extension"
module = "my_pkg._core"
```

### Jobs

Each job compiles a single Mojo source into an output artifact.

**Python extension:**

```toml
[[tool.hatch.build.targets.wheel.hooks.mojo.jobs]]
name = "core"
input = "src/mo/my_pkg/core.mojo"
emit = "python-extension"
module = "my_pkg._core"
include-dirs = ["src/mo"]
```

**Non-Python artifact** (requires an `install` mapping):

```toml
[[tool.hatch.build.targets.wheel.hooks.mojo.jobs]]
name = "cli"
input = "src/mo/my_pkg/cli.mojo"
emit = "executable"
install = { kind = "scripts", path = "my-cli" }
```

### Job options reference

| Option | Type | Description |
|---|---|---|
| `name` | string | Unique identifier for the job |
| `input` | string | Path to the Mojo source file (supports globs) |
| `emit` | string | `python-extension`, `shared-lib`, `static-lib`, `object`, `executable` |
| `output` | string | Explicit output path (overrides default) |
| `module` | string | Dotted import path (required for `python-extension`) |
| `install` | object | Install mapping for non-Python artifacts: `{ kind, path }` |
| `profiles` | list | Profile names to inherit settings from |
| `include-dirs` | list | Additional include directories passed as `-I` |
| `defines` | list | Values passed as `-D` flags to the compiler |
| `flags` | list | Extra flags passed to `mojo build` |
| `env` | object | Environment variables set during compilation |
| `platforms` | list | Restrict job to specific `sys.platform` values |
| `arch` | list | Restrict job to specific `platform.machine()` values |
| `marker` | string | PEP 508 marker expression for conditional inclusion |
| `depends-on` | list | Job names that must complete before this one |

Supported install kinds: `package`, `data`, `scripts`, `root`, `force-include`

## Runtime library bundling

When building wheels that include Mojo python-extensions, set `bundle-libs = true` to copy the Mojo runtime libraries into the wheel:

```toml
[tool.hatch.build.targets.wheel.hooks.mojo]
bundle-libs = true
```

This works on both Linux and macOS. On Linux, `patchelf` sets RPATH on each library. On macOS, `install_name_tool` rewrites dylib install names and inter-library references to use `@rpath`.

### cibuildwheel

When using [cibuildwheel](https://cibuildwheel.pypa.io/), keep the following in mind:

**Linux (manylinux):** The Mojo SDK requires `manylinux_2_34` or newer due to GLIBCXX requirements. Standard `auditwheel repair` may reject the wheel — use a retag command instead:

```toml
[tool.cibuildwheel.linux]
repair-wheel-command = "python -m wheel tags --remove --platform-tag manylinux_2_34_x86_64 {wheel} && mv {wheel} {dest_dir}"
```

**macOS:** With `bundle-libs = true`, macOS wheels work with standard `delocate`. No special repair command is needed:

```toml
[tool.cibuildwheel.macos]
repair-wheel-command = "delocate-wheel -w {dest_dir} {wheel}"
```

**macOS SIP and `DYLD_LIBRARY_PATH`:** macOS System Integrity Protection (SIP) strips `DYLD_LIBRARY_PATH` from child processes. Setting it in `CIBW_ENVIRONMENT` will **not** propagate to the repair step. If you need it, pass it inline in the repair command:

```toml
[tool.cibuildwheel.macos]
repair-wheel-command = "DYLD_LIBRARY_PATH=/path/to/libs delocate-wheel -w {dest_dir} {wheel}"
```

**libstdc++ on manylinux:** If the Mojo SDK links against a newer libstdc++ than the manylinux baseline provides, you may need to bundle it from conda-forge. This is a Mojo SDK limitation, not a hatch-mojo issue.

## Troubleshooting

| Error | Fix |
|---|---|
| `mojo executable not found` | Set `mojo-bin`, `HATCH_MOJO_BIN`, or add `mojo` to `PATH` |
| `No build jobs resolved` | Check `input` paths, `include`/`exclude` globs, and `targets` |
| `unknown dependencies` | Ensure `depends-on` references valid job names |
| Wheel missing binaries | Set `module` for extension jobs or `install` for non-Python jobs |

## License

MIT
