# Code Patterns and Idioms

Repository-wide Python conventions, slotted immutable value objects, and external binary wrapper patterns.

## Chapters

| Title | Type | Description | Tags |
| --- | --- | --- | --- |
| [Typed Slotted Value Models](typed-slotted-models.md) | Pattern | Frozen slotted dataclasses, tuple sequence fields, and strict dual-typechecker conventions across `hatch_mojo`. | `pattern`, `typing`, `dataclasses` |
| [Idempotent Binary Patching](idempotent-binary-patching.md) | Pattern | Subprocess CLI wrapper pattern surfacing `stderr` on failure while tolerating explicit idempotency substrings. | `pattern`, `subprocess`, `mach-o` |
