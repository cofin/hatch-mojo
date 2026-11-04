---
type: Task
id: wheel-tags-metadata-and-ci:t01
title: "Implement wheel-tag (auto/infer/py3-none/custom) config validation and register_artifacts platform tag resolution"
description: "Validate wheel-tag options in HookConfig and resolve Hatchling-compatible py3-none/infer/custom PEP 425 wheel tags in register_artifacts."
state: completed
priority: P1
verification_strategy: behavior_tdd
depends_on: []
files:
  - hatch_mojo/config.py
  - hatch_mojo/artifacts.py
  - hatch_mojo/plugin.py
tests:
  - tests/test_config.py
  - tests/test_artifacts.py
  - tests/test_plugin.py
  - tests/test_integration_wheel.py
plan_revision: 3
plan_commit: 7e10d5b
state_revision: 2
claimed_by: null
claimed_at: null
blocked_reason: null
unblock_condition: null
next_step: null
last_verified_at: 2026-11-04T20:12:11Z
last_verified_commit: 6d73892
verification_evidence: "uv run pytest tests/test_config.py tests/test_artifacts.py tests/test_plugin.py tests/test_integration_wheel.py -q (58 passed); ruff, mypy, pyright, slotscheck exit 0"
created_at: 2026-11-04T05:12:00Z
updated_at: 2026-11-04T20:12:56Z
commit: 6d73892
tags: [feature, wheel-tag, pep425, py3-none, hatchling]
---

# Task `t01`: Implement `wheel-tag` (`auto`/`infer`/`py3-none`/Custom) Config Validation and `register_artifacts` Platform Tag Resolution

## Objective

Add `wheel-tag` (`"auto" | "infer" | "py3-none" | "<pep425_tag>"`) to `HookConfig`, implement Hatchling-compatible `resolve_host_platform_tag` and tag policy routing in `register_artifacts`, and wire `wheel_tag` and `macos_max_compat` from `MojoBuildHook.initialize`.

## Context

- **Verification Strategy (`behavior_tdd`)**: Introduces `wheel-tag` policy resolution across `parse_config`, `register_artifacts`, `MojoBuildHook.initialize`, and real `uv build --wheel` builds.
- **Hatchling `WheelBuilder` Contract**: In `hatchling.builders.wheel.WheelBuilder.build_standard`, Hatchling uses `build_data["tag"]` directly when present, otherwise calls `get_best_matching_tag()` when `build_data["infer_tag"]` is `True`, and writes `Root-Is-Purelib: false` when `build_data["pure_python"]` is `False`. `resolve_host_platform_tag` must mirror `get_best_matching_tag()` (`packaging.tags.sys_tags()` skipping `"manylinux"`/`"musllinux"`, plus `hatchling.builders.macos.process_macos_plat_tag` on `sys.platform == "darwin"`).
- **Canonical Test Targets**: `tests/test_config.py`, `tests/test_artifacts.py`, `tests/test_plugin.py`, `tests/test_integration_wheel.py`.

## Steps

1. **Write failing unit and wheel integration tests (`RED`)**:
   - In `tests/test_config.py`:
     - Add `test_parse_config_wheel_tag_variants_and_validation` asserting default `config.wheel_tag == "auto"`, accepting `"infer"`, `"py3-none"`, and `"py3-none-manylinux_2_34_x86_64"` (plus `HATCH_MOJO_WHEEL_TAG` env override), raising `TypeError` on non-string values (`123`), and raising `ValueError` on malformed tags (`""`, `"bad"`, `"py3-none-"`).
   - In `tests/test_artifacts.py`:
     - Add `test_register_artifacts_wheel_tag_auto_extension_vs_standalone` verifying `"auto"` sets `infer_tag = True` (without `"tag"`) when a `python-extension` job is present, sets `infer_tag = False` + `pure_python = False` + `tag == f"py3-none-{plat}"` when only `executable`/`shared-lib` jobs exist, and leaves `pure_python`/`infer_tag`/`tag` unset when only `object`/`mojoc` jobs exist.
     - Add `test_register_artifacts_wheel_tag_py3_none_and_custom_and_darwin_compat` verifying `"py3-none"` on a `python-extension` wheel sets `tag = f"py3-none-{plat}"` and `infer_tag = False`, custom `"cp312-abi3-manylinux_2_34_x86_64"` sets `tag` verbatim, and `resolve_host_platform_tag(macos_max_compat=True)` invokes `process_macos_plat_tag` when `sys.platform == "darwin"` is monkeypatched.
   - In `tests/test_plugin.py`: update `_config()` helper with `wheel_tag: str = "auto"` and assert `MojoBuildHook.initialize` passes `wheel_tag=config.wheel_tag` and `macos_max_compat` to `register_artifacts`.
   - In `tests/test_integration_wheel.py`:
     - Add `test_wheel_build_py3_none_extension_and_auto_executable` running `uv build --wheel` on (a) a `python-extension` project with `wheel-tag = "py3-none"` and (b) a zero-`.py` standalone `executable`-only project (`install = { kind = "scripts", path = "my-cli" }`) with default `wheel-tag = "auto"`, asserting both emit `*-py3-none-*.whl` archives whose `.dist-info/WHEEL` metadata contains `Root-Is-Purelib: false` and `Tag: py3-none-`.
2. **Implement `wheel_tag` config, `resolve_host_platform_tag`, and `register_artifacts` routing (`GREEN`)**:
   - In `hatch_mojo/config.py`:
     - Add `wheel_tag: str = "auto"` to `HookConfig`.
     - Implement `_validate_wheel_tag(raw_val: Any) -> str` checking `os.getenv("HATCH_MOJO_WHEEL_TAG")` override when non-empty, enforcing `isinstance(..., str)`, allowing `{"auto", "infer", "py3-none"}`, and validating custom 3-part tags (`parts = val.split("-")`, `len(parts) == 3 and all(parts)`, and `packaging.tags.parse_tag(val)`).
   - In `hatch_mojo/artifacts.py`:
     - Implement `resolve_host_platform_tag(*, macos_max_compat: bool = False) -> str` using `packaging.tags.sys_tags()` (first tag with `"manylinux" not in t.platform and "musllinux" not in t.platform`) and `hatchling.builders.macos.process_macos_plat_tag(plat, compat=macos_max_compat)` when `sys.platform == "darwin"`.
     - Update `register_artifacts(*, root: Path, build_data: dict[str, Any], jobs: list[BuildJob], target_name: str, wheel_tag: str = "auto", macos_max_compat: bool = False) -> None` to implement `R1` (`auto` / `infer` / `py3-none` / explicit `<pep425_tag>`).
   - In `hatch_mojo/plugin.py`: pass `wheel_tag=config.wheel_tag` and `macos_max_compat=bool(getattr(getattr(self, "build_config", None), "macos_max_compat", False))` to `register_artifacts`.
3. **Refactor & verify**:
   - Run all static checks and `test_config`, `test_artifacts`, `test_plugin`, and `test_integration_wheel`.

## Verification

```bash
# Initial RED check
uv run pytest tests/test_config.py tests/test_artifacts.py tests/test_plugin.py tests/test_integration_wheel.py -q

# Final GREEN + static gates (all must exit 0)
uv run ruff check . && uv run ruff format --check . && uv run mypy && uv run pyright && uv run slotscheck hatch_mojo
uv run pytest tests/test_config.py tests/test_artifacts.py tests/test_plugin.py tests/test_integration_wheel.py -q
```

## Acceptance Criteria

- [x] `parse_config` validates `wheel-tag` (`"auto"`, `"infer"`, `"py3-none"`, or 3-part PEP 425 tag) and `HATCH_MOJO_WHEEL_TAG` (`R1`).
- [x] `register_artifacts` resolves `"auto"` to `"infer"` for extensions and `"py3-none"` for standalone native binaries, and emits `py3-none-<platform>` with `Root-Is-Purelib: false` when `"py3-none"` is active (`R1`).
- [x] `resolve_host_platform_tag` normalizes macOS platform tags via `process_macos_plat_tag` on `darwin` (`R1`).
- [x] `ruff`, `mypy`, `pyright`, `slotscheck`, and focused `pytest` modules exit `0`.

## Notes & Discoveries

_None._
