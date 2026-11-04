# Public-Seam Verification Guide (`hatch-build-pipeline`)

## Canonical Test Mapping

| Module Under Test | Canonical Test File | Public Seam Exercised |
| --- | --- | --- |
| `hatch_mojo/hooks.py` | `tests/test_hooks.py` | `hatch_register_build_hook()` |
| `hatch_mojo/config.py` | `tests/test_config.py` | `parse_config(raw, target_name=...)`, `matches_filters(...)` |
| `hatch_mojo/planner.py` | `tests/test_planner.py` | `plan_jobs(root, config)`, `plan_jobs_leveled(root, config)` |
| `hatch_mojo/compiler.py` | `tests/test_compiler.py`, `tests/test_integration_compile.py` | `discover_mojo(...)`, `build_command(...)`, `compute_job_digest(...)`, `compile_job(...)` |
| `hatch_mojo/artifacts.py` | `tests/test_artifacts.py` | `resolve_install_target(...)`, `resolve_host_platform_tag(...)`, `register_artifacts(...)` |
| `hatch_mojo/cleaning.py` | `tests/test_cleaning.py` | `save_manifest(...)`, `clean_from_manifest(...)`, `manifest_path(...)` |
| `hatch_mojo/plugin.py` | `tests/test_plugin.py`, `tests/test_integration_wheel.py` | `MojoBuildHook.{initialize,finalize,clean}(...)`, `WheelBuilder(..., versions=["editable"])`, `uv build --wheel` |

## Testing Rules

1. **Real Filesystem & Configs**: Construct real `.mojo` stub files in `tmp_path` and build `HookConfig` via `parse_config(...)` rather than mocking internal config/planner helpers.
2. **Synthetic Compiler Scripts for Integration**: Use executable `#!/usr/bin/env python3` scripts (`_write_fake_mojo` in `tests/test_integration_compile.py` and `tests/test_integration_wheel.py`, passing `--refresh-package hatch-mojo` to `uv build --wheel`) to exercise `compile_job`, digest caching, editable builds, and `uv build --wheel` end-to-end without requiring a local Modular SDK installation.
3. **Cross-Platform Simulation**: Only `monkeypatch` `sys.platform`, `shutil.which`, `importlib.import_module`, or `HATCH_MOJO_*` env vars to test OS-specific suffix maps, `mojo._package_root` discovery, and Windows `.exe`/`.cmd`/shebang handling.

## Focused Verification Commands

```bash
# Single module TDD loop
uv run pytest tests/test_planner.py -q

# End-to-end Hatchling wheel & editable hook verification
uv run pytest tests/test_integration_wheel.py -q

# Full static + slotscheck gate
uv run ruff check . && uv run ruff format --check . && uv run mypy && uv run pyright && uv run slotscheck hatch_mojo
```
