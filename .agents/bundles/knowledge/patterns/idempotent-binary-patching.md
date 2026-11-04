---
type: Pattern
title: Idempotent Binary Patching
description: Subprocess CLI wrapper pattern surfacing stderr on failure while tolerating explicit idempotency substrings.
status: stable
tags: [pattern, subprocess, mach-o]
generated:
  by: flow/0.26.0
  at: 2026-11-04T03:56:00Z
verified:
  - by: agent:flow-setup
    at: 2026-11-04T03:56:00Z
    commit: 1b6d139
sources:
  - id: install-name-helper
    resource: hatch_mojo/runtime.py::_run_install_name_tool
    title: Centralized install_name_tool subprocess wrapper with ignore_errors
  - id: strip-rpaths
    resource: hatch_mojo/runtime.py::_strip_absolute_rpaths
    title: Idempotent deletion of residual SDK LC_RPATH entries
  - id: patch-ext
    resource: hatch_mojo/runtime.py::_patch_macos_extension
    title: Idempotent addition of @loader_path RPATHs on macOS extensions
---

# Idempotent Binary Patching

<!-- truth: start -->
- Route all `install_name_tool` invocations through `hatch_mojo/runtime.py::_run_install_name_tool` with `capture_output=True, text=True`[^install-name-helper].
- Achieve idempotency by passing tool-emitted `stderr` substrings in `ignore_errors` (`["already contains LC_RPATH"]` on `-add_rpath`, `["no LC_RPATH found"]` on `-delete_rpath`), never by pre-checking `otool -l` output with brittle regexes[^install-name-helper][^strip-rpaths][^patch-ext].
- Always include captured `stderr` in raised `RuntimeError` messages when an unignored non-zero exit occurs (`ldd`, `otool`, `install_name_tool`, `mojo build`).
<!-- truth: end -->

## Canonical Pattern

`hatch_mojo/runtime.py::_run_install_name_tool`[^install-name-helper] executes the OS binary tool directly, inspects `exc.stderr` on `CalledProcessError`, returns cleanly when a known idempotent condition matches `ignore_errors`, and otherwise raises `RuntimeError(f"install_name_tool failed: {stderr}")`:

```python
def _run_install_name_tool(args: list[str], ignore_errors: list[str] | None = None) -> None:
    """Run install_name_tool and handle idempotency and error reporting."""
    try:
        subprocess.run(
            ["install_name_tool", *args],  # noqa: S607
            check=True,
            capture_output=True,
            text=True,
        )
    except subprocess.CalledProcessError as exc:
        stderr = exc.stderr or ""
        if ignore_errors and any(msg in stderr for msg in ignore_errors):
            return
        msg = f"install_name_tool failed: {stderr}"
        raise RuntimeError(msg) from exc
```

Reason: Pre-filtering `otool -l` load commands with custom regexes missed Mojo-emitted RPATH formatting variations and hid `install_name_tool` `stderr` diagnostics on failure[^strip-rpaths][^patch-ext].

## Anti-Patterns to Reject

- Calling `subprocess.run(..., capture_output=True, check=True)` on external linker/compiler tools without translating `CalledProcessError.stderr` into an actionable error message.
- Parsing human-oriented `otool` headers to guess whether an RPATH mutation will succeed when the underlying tool already reports idempotent conflict strings deterministically.

## Provenance

[^install-name-helper]: `hatch_mojo/runtime.py::_run_install_name_tool` — Wraps `install_name_tool` with `stderr` capture and `ignore_errors` matching.
[^strip-rpaths]: `hatch_mojo/runtime.py::_strip_absolute_rpaths` — Uses `ignore_errors=["no LC_RPATH found"]` when stripping absolute SDK RPATHs.
[^patch-ext]: `hatch_mojo/runtime.py::_patch_macos_extension` — Uses `ignore_errors=["already contains LC_RPATH"]` when adding `@loader_path` RPATHs.
