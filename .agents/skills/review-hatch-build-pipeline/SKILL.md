---
name: review-hatch-build-pipeline
description: "Use when reviewing specifications or Git diffs touching hatch_mojo/{hooks,plugin,config,types,planner,compiler,artifacts,cleaning}.py, pyproject.toml, Makefile, or tests/test_{hooks,plugin,config,planner,compiler,artifacts,cleaning,integration_compile,integration_wheel}.py."
---

# Zero-Context Review Lens: Hatch Build Pipeline (`review-hatch-build-pipeline`)

<!-- truth: start -->
- Evaluate changes strictly against [`references/checklist.md`](references/checklist.md) (`HBP-01` through `HBP-08`) and suppress every intentional repository pattern documented in [`references/false-positive-suppressions.md`](references/false-positive-suppressions.md) (`FP-HBP-01` through `FP-HBP-05`).
- Bind every finding to concrete `file:line` and `path/to/file::Symbol` evidence from the inspected diff or spec.
- Flag any unslotted/mutable dataclass in `hatch_mojo/`, broken wheel tag purity invariants, swallowed compiler `stderr`, inline `#` restatement comments, or non-canonical test file sprawl.
<!-- truth: end -->

## Workflow

1. Load [`references/checklist.md`](references/checklist.md) and [`references/false-positive-suppressions.md`](references/false-positive-suppressions.md).
2. Read the exact `base_commit..head_commit` diff (or `spec.md` + `tasks/*.md` worksheets) and inspect surrounding definitions in `hatch_mojo/`.
3. Check every modified symbol against `HBP-01..HBP-08`, filtering out `FP-HBP-01..FP-HBP-05`.
4. Emit findings ordered by severity (`Critical`, `Important`, `Minor`) with `HBP-XX` rule IDs and `path/to/file::Symbol` citations.

## References

- [Domain Review Checklist (`HBP-01..HBP-08`)](references/checklist.md)
- [False-Positive Suppressions (`FP-HBP-01..FP-HBP-05`)](references/false-positive-suppressions.md)
