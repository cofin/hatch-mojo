"""Mojo runtime library discovery, bundling, and RPATH patching."""

from __future__ import annotations

import importlib.util
import os
import shutil
import subprocess
import sys
from pathlib import Path

from hatch_mojo.types import BuildJob

_RUNTIME_LIB_BASES: tuple[str, ...] = (
    "KGENCompilerRTShared",
    "AsyncRTRuntimeGlobals",
    "MSupportGlobals",
    "NVPTX",
    "AsyncRTMojoBindings",
)

_SENTINEL = "libKGENCompilerRTShared.so"


def _lib_filename(base: str) -> str:
    """Return platform-appropriate shared library filename."""
    if sys.platform == "darwin":
        return f"lib{base}.dylib"
    return f"lib{base}.so"


def discover_modular_lib(root: Path, mojo_bin: str | None) -> Path:
    """Find the ``modular/lib/`` directory containing Mojo runtime libraries.

    Search order:
    1. ``MODULAR_LIB_DIR`` environment variable
    2. ``importlib.util.find_spec("modular")``
    3. Walk up from the mojo binary
    4. Well-known cibuildwheel container paths
    """
    env_dir = os.environ.get("MODULAR_LIB_DIR")
    if env_dir:
        path = Path(env_dir)
        if (path / _SENTINEL).exists():
            return path

    spec = importlib.util.find_spec("modular")
    if spec and spec.origin:
        candidate = Path(spec.origin).parent / "lib"
        if (candidate / _SENTINEL).exists():
            return candidate

    if mojo_bin:
        cursor = Path(mojo_bin).resolve().parent
        for _ in range(5):
            candidate = cursor / "lib"
            if (candidate / _SENTINEL).exists():
                return candidate
            if cursor.parent == cursor:
                break
            cursor = cursor.parent

    for container_path in (
        Path("/opt/modular/lib"),
        root / ".modular" / "lib",
    ):
        if (container_path / _SENTINEL).exists():
            return container_path

    msg = (
        "Could not locate Mojo runtime libraries (modular/lib). "
        "Set MODULAR_LIB_DIR or ensure the modular package is importable."
    )
    raise FileNotFoundError(msg)


def _compute_extension_rpath(module: str, pkg_name: str) -> str:
    """Compute the RPATH for a python-extension based on its module depth.

    ``mogemma._core`` (depth 1) → ``$ORIGIN:$ORIGIN/../mogemma.libs``
    ``pkg.sub._core`` (depth 2) → ``$ORIGIN:$ORIGIN/../../pkg.libs``
    """
    origin = "@loader_path" if sys.platform == "darwin" else "$ORIGIN"
    parts = module.split(".")
    depth = len(parts) - 1
    up = "/".join(".." for _ in range(depth))
    return f"{origin}:{origin}/{up}/{pkg_name}.libs"


def _patch_rpath(target: Path, rpath: str) -> None:
    """Set RPATH on a shared library or extension."""
    if sys.platform == "win32":
        return
    if sys.platform == "darwin":
        subprocess.run(
            ["install_name_tool", "-add_rpath", rpath, str(target)],  # noqa: S607
            check=True,
            capture_output=True,
        )
    else:
        subprocess.run(
            ["patchelf", "--set-rpath", rpath, str(target)],  # noqa: S607
            check=True,
            capture_output=True,
        )


def bundle_runtime_libs(
    root: Path,
    build_dir: str,
    jobs: list[BuildJob],
    mojo_bin: str | None,
) -> dict[str, str]:
    """Bundle Mojo runtime libs alongside python-extension outputs.

    Returns a mapping of ``{staging_path: wheel_relative_path}`` suitable
    for merging into Hatch ``force_include``.
    """
    if sys.platform == "win32":
        return {}

    ext_jobs = [j for j in jobs if j.emit == "python-extension" and j.module]
    if not ext_jobs:
        return {}

    modular_lib = discover_modular_lib(root, mojo_bin)

    # Group extension jobs by top-level package
    packages: dict[str, list[BuildJob]] = {}
    for job in ext_jobs:
        pkg = job.module.split(".")[0]  # type: ignore[union-attr]
        packages.setdefault(pkg, []).append(job)

    force_include: dict[str, str] = {}
    abs_build = root / build_dir

    for pkg_name, pkg_jobs in packages.items():
        libs_dir = abs_build / f"{pkg_name}.libs"
        libs_dir.mkdir(parents=True, exist_ok=True)

        for base in _RUNTIME_LIB_BASES:
            filename = _lib_filename(base)
            src = modular_lib / filename
            if not src.exists():
                msg = f"Missing required Mojo runtime library: {src}"
                raise FileNotFoundError(msg)
            dest = libs_dir / filename
            shutil.copy2(src, dest)

            origin = "@loader_path" if sys.platform == "darwin" else "$ORIGIN"
            _patch_rpath(dest, origin)

            force_include[str(dest)] = f"{pkg_name}.libs/{filename}"

        for job in pkg_jobs:
            rpath = _compute_extension_rpath(job.module, pkg_name)  # type: ignore[arg-type]
            _patch_rpath(job.output_path, rpath)

    return force_include
