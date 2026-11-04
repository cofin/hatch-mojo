---
name: review-native-runtime-bundling
description: "Use when reviewing specifications or Git diffs touching hatch_mojo/runtime.py, Darwin linker flags in hatch_mojo/compiler.py, or runtime bundling tests in tests/test_runtime.py."
---

# Zero-Context Review Lens: Native Runtime Bundling (`review-native-runtime-bundling`)

<!-- truth: start -->
- Evaluate changes strictly against [`references/checklist.md`](references/checklist.md) (`NRB-01` through `NRB-08`) and suppress every intentional repository pattern documented in [`references/false-positive-suppressions.md`](references/false-positive-suppressions.md) (`FP-NRB-01` through `FP-NRB-05`).
- Bind every finding to concrete `file:line` and `path/to/file::Symbol` evidence from the inspected diff or spec.
- Prioritize Mach-O signature validity (`codesign` after every `install_name_tool` pass), residual SDK RPATH stripping, dynamic dependency walking, writable copy permissions, and surfaced subprocess `stderr`.
<!-- truth: end -->

## Workflow

1. Load [`references/checklist.md`](references/checklist.md) and [`references/false-positive-suppressions.md`](references/false-positive-suppressions.md).
2. Read the exact `base_commit..head_commit` diff (or `spec.md` + `tasks/*.md` worksheets) and inspect `hatch_mojo/runtime.py` and `tests/test_runtime.py`.
3. Check every modified path against `NRB-01..NRB-08`, filtering out `FP-NRB-01..FP-NRB-05`.
4. Emit findings ordered by severity (`Critical`, `Important`, `Minor`) with `NRB-XX` rule IDs and `path/to/file::Symbol` citations.

## References

- [Domain Review Checklist (`NRB-01..NRB-08`)](references/checklist.md)
- [False-Positive Suppressions (`FP-NRB-01..FP-NRB-05`)](references/false-positive-suppressions.md)
