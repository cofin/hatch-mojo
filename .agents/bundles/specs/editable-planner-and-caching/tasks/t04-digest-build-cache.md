---
type: Task
id: editable-planner-and-caching:t04
title: "Add thread-safe SHA-256 cache.json incremental compilation and cleanup integration"
description: "Cache SHA-256 job digests and pristine .raw compiler outputs thread-safely in compile_job, restoring clean binaries on cache hits and cleaning cache state."
state: pending
priority: P1
verification_strategy: behavior_tdd
depends_on:
  - editable-planner-and-caching:t03
files:
  - hatch_mojo/compiler.py
  - hatch_mojo/cleaning.py
  - hatch_mojo/plugin.py
tests:
  - tests/test_compiler.py
  - tests/test_cleaning.py
  - tests/test_plugin.py
  - tests/test_integration_compile.py
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
updated_at: 2026-11-04T06:04:00Z
commit: null
tags: [performance, compiler, cache, sha256]
---

# Task `t04`: Add Thread-Safe SHA-256 `cache.json` Incremental Compilation and Cleanup Integration

## Objective

Implement deterministic SHA-256 input/include/flag/compiler digest caching (`<build_dir>/cache.json`) inside `compile_job` so unchanged jobs skip `mojo` subprocess execution when `config.cache` is `True`, and remove `cache.json` during `clean_from_manifest`.

## Context

- **Verification Strategy (`behavior_tdd`)**: Verifies cache-hit subprocess elision and cache invalidation across source edits, `-I` transitive `.mojo` header edits, flag/define/env edits, missing outputs, and `cache = false` through `compile_job` and `clean_from_manifest` seams.
- **Concurrency Invariant**: Guard `<build_dir>/cache.json` reads/writes with a module-level `threading.Lock` so parallel `ThreadPoolExecutor` waves never lose updates or read partial JSON.
- **Canonical Test Targets**: `tests/test_compiler.py`, `tests/test_cleaning.py`, `tests/test_plugin.py`, `tests/test_integration_compile.py`.

## Steps

1. **Write failing unit and integration tests (`RED`)**:
   - In `tests/test_compiler.py` and `tests/test_integration_compile.py`:
     - Add `test_compile_job_cache_hit_restores_pristine_raw_binary_and_invalidates_on_changes` using a `#!/usr/bin/env python3` fake `mojo` script (`win32`-compatible via `_has_shebang`) that increments an invocation counter file, asserting: (1) run 1 compiles (`count == 1`) and stores `<cache_dir>/.raw/<digest><suffix>`; (2) mutating `job.output_path` in place (simulating `patchelf` / `install_name_tool` RPATH edits) or deleting `job.output_path` and running a second time restores pristine bytes from `.raw` with `"cache=hit"` (`count == 1`); (3) modifying a nested `.mojo` or `.mojoc` file under `include_dirs` (`rglob`) invalidates the digest (`count == 2`); (4) modifying a linked `.o` file referenced in `job.flags` or `flags`/`defines` invalidates the digest (`count == 3`); and (5) deleting `.raw` forces recompilation (`count == 4`).
     - Add `test_compile_job_cache_disabled_always_compiles` verifying `use_cache=False` invokes `mojo` on every call.
   - In `tests/test_cleaning.py`: add assertion verifying `clean_from_manifest` deletes `<build_dir>/cache.json` and `<build_dir>/.raw/` alongside `manifest.json` and prunes `<build_dir>`.
   - In `tests/test_plugin.py`: verify `MojoBuildHook.initialize` forwards `use_cache=config.cache` and `cache_dir=root / config.build_dir` to `compile_job`.
2. **Implement SHA-256 digest computation, `.raw` artifact restoration, `cache.json` persistence, and cleanup (`GREEN`)**:
   - In `hatch_mojo/compiler.py`:
     - Define `CACHE_FILENAME = "cache.json"`, `RAW_CACHE_DIRNAME = ".raw"`, and `_CACHE_LOCK = threading.Lock()`.
     - Implement `compute_job_digest(*, mojo_bin: str, root: Path, job: BuildJob, cache_dir: Path | None = None) -> str` resolving `resolved_bin = shutil.which(mojo_bin) or mojo_bin` before statting `(resolved_path, st_mtime_ns, st_size)`, hashing JSON-serialized metadata (`compiler_fingerprint`, `job.emit`, `job.module`, `job.flags`, `job.defines`, `job.include_dirs`, `sorted(job.env.items())`, `job.depends_on`, `str(job.output_path)`) plus `(rel_path, sha256_hex)` pairs for `job.input_path`, all sorted `rglob("*.mojo")` and `rglob("*.mojoc")` files under `job.input_path.parent` (skipping `cache_dir` unless `cache_dir` is explicitly inside `job.include_dirs`) and each `inc_dir`, any existing file paths in `job.flags` (resolved relative to `root`), and any upstream `job.depends_on` digests recorded in `cache.json`.
     - Extend `compile_job(*, mojo_bin: str, root: Path, job: BuildJob, fail_fast: bool = True, use_cache: bool = False, cache_dir: Path | None = None) -> tuple[bool, str]`: when `use_cache and cache_dir is not None`, compute digest; if `cache.get(job.name) == digest` and `(cache_dir / RAW_CACHE_DIRNAME / f"{digest}{job.output_path.suffix}").is_file()`, copy that pristine `.raw` file onto `job.output_path` (`job.output_path.parent.mkdir(parents=True, exist_ok=True)`) and return `(True, f"job={job.name}\ncache=hit\noutput={job.output_path}")`; after a successful `mojo` run, copy `job.output_path` (when `is_file()`) into `<cache_dir>/.raw/<digest><suffix>` and persist `cache[job.name] = digest` under `_CACHE_LOCK`.
   - In `hatch_mojo/cleaning.py::clean_from_manifest`: unlink `(root / build_dir / "cache.json")` (`missing_ok=True`) and `shutil.rmtree(root / build_dir / ".raw", ignore_errors=True)` before pruning empty `build_dir` directories.
   - In `hatch_mojo/plugin.py`: pass `use_cache=config.cache, cache_dir=root / config.build_dir` to every `compile_job` call.
3. **Refactor & verify**:
   - Run full Chapter 3 recovery checkpoint gates (`ruff`, `mypy`, `pyright`, `slotscheck`, and full `pytest`).

## Verification

```bash
# Initial RED check
uv run pytest tests/test_compiler.py tests/test_cleaning.py tests/test_plugin.py tests/test_integration_compile.py -q

# Final GREEN + Chapter 3 Recovery Checkpoint (all must exit 0)
uv run ruff check . && uv run ruff format --check . && uv run mypy && uv run pyright && uv run slotscheck hatch_mojo
uv run pytest -q
```

## Acceptance Criteria

- [ ] `compute_job_digest` incorporates compiler stat metadata, flags/defines/env, `input_path`, linked `flags` files, upstream `depends_on` digests, and recursive `*.mojo`/`*.mojoc` files in `input_path.parent` and `include_dirs` (`R4`).
- [ ] `compile_job` restores pristine unpatched binaries from `<build_dir>/.raw/<digest><suffix>` on cache hit when `use_cache=True`, and updates `.raw/` + `<build_dir>/cache.json` thread-safely on compile success (`R4`).
- [ ] `clean_from_manifest` removes `cache.json` and `.raw/` and prunes empty directories (`R4`).
- [ ] Full static analysis and `pytest` suite exit `0`.

## Notes & Discoveries

_None._
