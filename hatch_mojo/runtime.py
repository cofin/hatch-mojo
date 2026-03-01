"""Mojo runtime library discovery, bundling, and RPATH patching."""

from __future__ import annotations

import importlib.util
import os
import re
import shutil
import stat
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


def _lib_filename(base: str) -> str:
    """Return platform-appropriate shared library filename."""
    if sys.platform == "darwin":
        return f"lib{base}.dylib"
    return f"lib{base}.so"


def _sentinel() -> str:
    """Return the platform-appropriate sentinel filename for library discovery."""
    return _lib_filename(_RUNTIME_LIB_BASES[0])


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
        if (path / _sentinel()).exists():
            return path

    spec = importlib.util.find_spec("modular")
    if spec:
        if spec.origin:
            candidate = Path(spec.origin).parent / "lib"
            if (candidate / _sentinel()).exists():
                return candidate
        if spec.submodule_search_locations:
            for loc in spec.submodule_search_locations:
                candidate = Path(loc) / "lib"
                if (candidate / _sentinel()).exists():
                    return candidate

    if mojo_bin:
        cursor = Path(mojo_bin).resolve().parent
        for _ in range(5):
            candidate = cursor / "lib"
            if (candidate / _sentinel()).exists():
                return candidate
            if cursor.parent == cursor:
                break
            cursor = cursor.parent

    for container_path in (
        Path("/opt/modular/lib"),
        root / ".modular" / "lib",
    ):
        if (container_path / _sentinel()).exists():
            return container_path

    msg = (
        "Could not locate Mojo runtime libraries (modular/lib). "
        "Set MODULAR_LIB_DIR or ensure the modular package is importable."
    )
    raise FileNotFoundError(msg)


_MOJO_RUNTIME_NOTICE = """\
This directory contains Mojo runtime libraries bundled from the Modular SDK.

Bundled libraries:
{lib_list}

These libraries are copyright Modular Inc. and are distributed under the
Modular Community License. The full license text is available at:

    https://modular.com/legal/max-mojo-license

By using this software you agree to the terms of the Modular Community License.
"""


def _write_license_notice(
    libs_dir: Path,
    lib_filenames: list[str],
    modular_lib: Path,
) -> list[tuple[str, str]]:
    """Write license notices for bundled Mojo runtime libraries.

    Returns a list of (abs_path, wheel_relative_path) entries for force_include.
    """
    pkg_libs = libs_dir.name  # e.g. "mogemma.libs"
    entries: list[tuple[str, str]] = []

    # Generate notice file
    lib_list = "\n".join(f"  - {f}" for f in sorted(lib_filenames))
    notice = libs_dir / "NOTICE.mojo-runtime"
    notice.write_text(_MOJO_RUNTIME_NOTICE.format(lib_list=lib_list))
    entries.append((str(notice), f"{pkg_libs}/NOTICE.mojo-runtime"))

    # Copy SDK LICENSE if present
    sdk_license = modular_lib.parent / "LICENSE"
    if sdk_license.is_file():
        dest = libs_dir / "LICENSE.mojo-runtime"
        shutil.copy2(sdk_license, dest)
        entries.append((str(dest), f"{pkg_libs}/LICENSE.mojo-runtime"))

    return entries


_OTOOL_LIB_RE: re.Pattern[str] = re.compile(r"^\s+(.+?)\s+\(compatibility version")
_OTOOL_RPATH_RE: re.Pattern[str] = re.compile(r"^\s+path\s+(.+?)(?:\s+\(offset .+\))?$")


def _get_linked_libraries(target: Path) -> list[str]:
    """Return library paths that *target* links against (macOS ``otool -L``)."""
    result = subprocess.run(
        ["otool", "-L", str(target)],  # noqa: S607
        check=True,
        capture_output=True,
        text=True,
    )
    libs: list[str] = []
    for line in result.stdout.splitlines()[1:]:  # skip first line (binary name)
        m = _OTOOL_LIB_RE.match(line)
        if m:
            libs.append(m.group(1))
    return libs


def _strip_absolute_rpaths(target: Path) -> None:
    """Remove absolute RPATHs from a Mach-O binary.

    Bundled dylibs may carry residual RPATHs from the SDK build environment
    (e.g. ``/opt/modular/lib``).  Stripping them prevents the dynamic linker
    from accidentally loading a different version from the SDK on developer
    machines.
    """
    result = subprocess.run(
        ["otool", "-l", str(target)],  # noqa: S607
        check=True,
        capture_output=True,
        text=True,
    )
    for line in result.stdout.splitlines():
        m = _OTOOL_RPATH_RE.match(line)
        if m:
            rpath = m.group(1)
            if not rpath.startswith("@"):
                subprocess.run(
                    ["install_name_tool", "-delete_rpath", rpath, str(target)],  # noqa: S607
                    check=True,
                    capture_output=True,
                )


def _has_rpath(target: Path, rpath: str) -> bool:
    """Check whether *target* already contains the given LC_RPATH entry."""
    result = subprocess.run(
        ["otool", "-l", str(target)],  # noqa: S607
        check=True,
        capture_output=True,
        text=True,
    )
    for line in result.stdout.splitlines():
        m = _OTOOL_RPATH_RE.match(line)
        if m and m.group(1) == rpath:
            return True
    return False


def _resign_ad_hoc(target: Path) -> None:
    """Ad-hoc re-sign a binary after modifying it with ``install_name_tool``.

    On macOS (especially arm64), modifying a signed binary invalidates its
    code signature.  The OS loader will refuse to load it at runtime
    (``EXC_BAD_ACCESS`` / ``killed: 9``).  An ad-hoc signature restores a
    valid (but identity-less) signature that satisfies the loader.
    """
    subprocess.run(
        ["codesign", "-s", "-", "-f", str(target)],  # noqa: S607
        check=True,
        capture_output=True,
    )


def _patch_macos_dylibs(libs_dir: Path, lib_filenames: list[str]) -> None:
    """Rewrite install names for all bundled dylibs in *libs_dir*.

    For each dylib:
    - Change its own identity (LC_ID_DYLIB) to ``@rpath/<filename>``
    - Rewrite references to sibling dylibs from absolute paths to ``@rpath/<basename>``
    - Ad-hoc re-sign to keep the code signature valid
    """
    for filename in lib_filenames:
        target = libs_dir / filename
        # Strip residual absolute RPATHs from SDK build environment
        _strip_absolute_rpaths(target)
        # Change own identity
        subprocess.run(
            ["install_name_tool", "-id", f"@rpath/{filename}", str(target)],  # noqa: S607
            check=True,
            capture_output=True,
        )
        # Rewrite sibling references
        linked = _get_linked_libraries(target)
        for ref in linked:
            if ref.startswith(("@rpath/", "@loader_path/")):
                continue
            if ref.startswith(("/usr/lib/", "/System/")):
                continue
            basename = Path(ref).name
            if basename in lib_filenames:
                subprocess.run(
                    [  # noqa: S607
                        "install_name_tool",
                        "-change",
                        ref,
                        f"@rpath/{basename}",
                        str(target),
                    ],
                    check=True,
                    capture_output=True,
                )
        _resign_ad_hoc(target)


def _patch_macos_extension(ext: Path, lib_filenames: list[str], rpath: str) -> None:
    """Rewrite an extension's references to bundled dylibs and add RPATH."""
    linked = _get_linked_libraries(ext)
    for ref in linked:
        if ref.startswith(("@rpath/", "@loader_path/")):
            continue
        if ref.startswith(("/usr/lib/", "/System/")):
            continue
        basename = Path(ref).name
        if basename in lib_filenames:
            subprocess.run(
                [  # noqa: S607
                    "install_name_tool",
                    "-change",
                    ref,
                    f"@rpath/{basename}",
                    str(ext),
                ],
                check=True,
                capture_output=True,
            )
    if not _has_rpath(ext, rpath):
        subprocess.run(
            ["install_name_tool", "-add_rpath", rpath, str(ext)],  # noqa: S607
            check=True,
            capture_output=True,
        )
    _resign_ad_hoc(ext)


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

        # Copy all runtime libs
        lib_filenames: list[str] = []
        for base in _RUNTIME_LIB_BASES:
            filename = _lib_filename(base)
            src = modular_lib / filename
            if not src.exists():
                msg = f"Missing required Mojo runtime library: {src}"
                raise FileNotFoundError(msg)
            dest = libs_dir / filename
            shutil.copy2(src, dest)
            dest.chmod(dest.stat().st_mode | stat.S_IWUSR)
            lib_filenames.append(filename)
            force_include[str(dest)] = f"{pkg_name}.libs/{filename}"

        # Add license notice for bundled libraries
        force_include.update(_write_license_notice(libs_dir, lib_filenames, modular_lib))

        if sys.platform == "darwin":
            # Rewrite dylib install names and inter-library references
            _patch_macos_dylibs(libs_dir, lib_filenames)
            for job in pkg_jobs:
                rpath = _compute_extension_rpath(job.module, pkg_name)  # type: ignore[arg-type]
                _patch_macos_extension(job.output_path, lib_filenames, rpath)
        else:
            # Linux: set RPATH on each copied lib and extension
            for filename in lib_filenames:
                _patch_rpath(libs_dir / filename, "$ORIGIN")
            for job in pkg_jobs:
                rpath = _compute_extension_rpath(job.module, pkg_name)  # type: ignore[arg-type]
                _patch_rpath(job.output_path, rpath)

    return force_include
