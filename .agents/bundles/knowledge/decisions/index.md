# Architectural Decision Records

Decisions that pass the three-part ADR filter: **hard to reverse**, **surprising without context**, and involving a **genuine trade-off**.

## Records

| Title | Type | Description | Tags |
| --- | --- | --- | --- |
| [ADR-001: Dynamic Runtime Dependency Resolution](adr-001-dynamic-runtime-dependency-resolution.md) | Decision | Resolve Modular runtime libraries dynamically via recursive `ldd` / `otool -L` walking bounded by `modular/lib` and `libKGENCompilerRTShared`. | `decision`, `runtime`, `bundling` |
| [ADR-002: Idempotent Mach-O RPATH Patching and Ad-Hoc Signing](adr-002-idempotent-macho-rpath-patching.md) | Decision | Patch Mach-O dylibs and extensions directly via `_run_install_name_tool` error-substring idempotency plus ad-hoc `codesign`. | `decision`, `macos`, `mach-o` |
