---
type: Task
id: editable-planner-and-caching:t01
title: "Deep-merge profile sequences/dicts, tighten jobs/install validation, and add skip-editable=false & cache=true defaults"
description: "Concatenate profile flags/lists, validate jobs/install shapes strictly, and add skip_editable=False and cache=True defaults with env overrides."
state: pending
priority: P1
verification_strategy: regression_tdd
depends_on: []
files:
  - hatch_mojo/config.py
tests:
  - tests/test_config.py
  - tests/test_plugin.py
plan_revision: 3
plan_commit: null
state_revision: 0
claimed_by: null
claimed_at: null
blocked_reason: null
unblock_condition: null
next_step: null
last_verified_at: null
last_verified_commit: null
verification_evidence: null
created_at: 2026-11-04T05:05:00Z
updated_at: 2026-11-04T06:13:00Z
commit: null
tags: [bugfix, config, profiles, editable, cache]
---

# Task `t01`: Deep-Merge Profile Sequences/Dicts, Tighten `jobs`/`install` Validation, and Add `skip-editable=false` & `cache=true` Defaults

## Objective

Fix `hatch_mojo/config.py` so profile list and dict fields merge instead of overwriting, `{"jobs": {}}` and invalid `install` shapes fail with proper `TypeError`/`ValueError`, `skip_editable` defaults to `False` (`HATCH_MOJO_SKIP_EDITABLE` override), and `HookConfig` exposes `cache: bool = True` (`HATCH_MOJO_CACHE` override).

## Context

- **Verification Strategy (`regression_tdd`)**: Fixes concrete `parse_config` defects (`{"jobs": {}}` falsy coercion, shallow `_merge_dict`, ignored `install` on extensions) while adding `cache` and `skip_editable=False` defaults.
- **Invariants**: `HookConfig` and `JobConfig` remain `@dataclass(slots=True, frozen=True)` (`HBP-01`). Never deduplicate `flags` tokens so repeated `["-Xlinker", "..."]` pairs preserve exact order.
- **Canonical Test Targets**: `tests/test_config.py`, `tests/test_plugin.py`.

## Steps

1. **Write failing unit tests (`RED`)**:
   - In `tests/test_config.py`:
     - Update `test_parse_config_invalid_jobs_type` to assert `pytest.raises(TypeError, match="jobs/sources must be a list")` on `{"jobs": {}}` and `{"sources": 123}`.
     - Add `test_parse_config_profile_deep_merge` verifying multiple profiles + job overrides concatenate `flags` verbatim (preserving repeated `"-Xlinker"` entries), concatenate and order-deduplicate `include-dirs`, `defines`, and `depends-on` across snake_case/kebab-case aliases, and merge `env` dicts with job keys winning on conflict.
     - Add `test_parse_config_rejects_non_dict_install_and_extension_install` asserting `TypeError` when `install = "bin"`, `ValueError` when `install = {"kind": "scripts", "path": " / "}` (empty stripped path for non-`root` install kind), and `ValueError` when `emit = "python-extension"` also sets `install = {"kind": "root", "path": "x"}`.
     - Add `test_parse_config_skip_editable_and_cache_defaults_and_env_overrides` asserting `config.skip_editable is False` and `config.cache is True` by default, and verifying `HATCH_MOJO_SKIP_EDITABLE="1"` / `HATCH_MOJO_CACHE="false"` override `pyproject.toml` booleans.
   - In `tests/test_plugin.py`: add `cache: bool = True` to `_config()` helper so `MojoBuildHook` tests remain aligned with `HookConfig`.
2. **Implement config validation, deep profile merge, and env overrides (`GREEN`)**:
   - In `hatch_mojo/config.py`:
     - Add `cache: bool` field to `HookConfig`.
     - Add `_env_bool(env_name: str, raw_val: Any, default: bool) -> bool` parsing `os.getenv(env_name)` (`"1"/"true"/"yes"/"on"` &rarr; `True`, `"0"/"false"/"no"/"off"` &rarr; `False`, raising `ValueError` on invalid non-empty env strings) ahead of `_bool(raw_val, default)`.
     - Replace `_merge_dict` with `_merge_job_dicts(base: dict[str, Any], extra: dict[str, Any]) -> dict[str, Any]` normalizing alias keys (`include_dirs` &rarr; `include-dirs`, `depends_on` &rarr; `depends-on`, `extra-args`/`extra_args` &rarr; `flags`), concatenating `flags` verbatim, deduplicating `include-dirs`/`defines`/`depends-on` via `dict.fromkeys(...)`, and merging `env` dicts.
     - Fix `jobs_raw` resolution (`raw["jobs"]` if `"jobs"` in `raw` and `raw["jobs"] is not None` else `raw.get("sources")` if `"sources"` in `raw` and `raw["sources"] is not None` else `[]`), raising `TypeError` when not a `list`.
     - Tighten `install` checks in `_validate_job` (`TypeError` if `install_cfg is not None and not isinstance(install_cfg, dict)`; `ValueError` if `emit_value == "python-extension" and install_cfg is not None`; replace `if install_kind and not install_path:` with `if install_kind and install_kind != "root" and (not install_path or not str(install_path).strip().strip("/")):` so `{"kind": "root"}` without `path` is valid while non-`root` kinds reject missing or slash-only paths; populate `cache` and `skip_editable` in both inactive-target and active returns of `parse_config`, clearing `HATCH_MOJO_*` env vars via `monkeypatch.delenv` in default tests).
3. **Refactor & verify**:
   - Run static checks and `tests/test_config.py` + `tests/test_plugin.py`.

## Verification

```bash
# Initial RED check
uv run pytest tests/test_config.py tests/test_plugin.py -q

# Final GREEN + static gates (all must exit 0)
uv run ruff check . && uv run ruff format --check . && uv run mypy && uv run pyright && uv run slotscheck hatch_mojo
uv run pytest tests/test_config.py tests/test_plugin.py -q
```

## Acceptance Criteria

- [ ] `parse_config({"jobs": {}}, target_name="wheel")` raises `TypeError` (`R1`).
- [ ] Profile + job merging preserves repeated `flags` tokens in order, deduplicates `include-dirs`/`defines`/`depends-on`, and merges `env` dicts (`R1`).
- [ ] `HookConfig` defaults to `skip_editable=False` and `cache=True`, honoring `HATCH_MOJO_SKIP_EDITABLE` and `HATCH_MOJO_CACHE` (`R1`).
- [ ] `ruff`, `mypy`, `pyright`, `slotscheck`, and focused `pytest` modules exit `0`.

## Notes & Discoveries

_None._
