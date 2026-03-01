from __future__ import annotations

import stat
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

import pytest

from hatch_mojo.runtime import (
    _RUNTIME_LIB_BASES,
    _compute_extension_rpath,
    _get_linked_libraries,
    _has_rpath,
    _lib_filename,
    _patch_macos_dylibs,
    _patch_macos_extension,
    _patch_rpath,
    _resign_ad_hoc,
    _sentinel,
    _strip_absolute_rpaths,
    bundle_runtime_libs,
    discover_modular_lib,
)
from hatch_mojo.types import BuildJob

# ── helpers ──────────────────────────────────────────────────────────────────


def _make_modular_lib(base: Path) -> Path:
    """Create a fake modular/lib directory with the sentinel and all runtime libs."""
    lib_dir = base / "lib"
    lib_dir.mkdir(parents=True, exist_ok=True)
    (lib_dir / _sentinel()).write_bytes(b"")
    for name in _RUNTIME_LIB_BASES:
        (lib_dir / _lib_filename(name)).write_bytes(b"fake-lib")
    return lib_dir


def _ext_job(tmp_path: Path, *, module: str = "pkg._core", name: str = "core") -> BuildJob:
    output = tmp_path / "build" / "mojo" / f"{name}.so"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(b"fake-ext")
    return BuildJob(
        name=name,
        input_path=tmp_path / f"{name}.mojo",
        output_path=output,
        emit="python-extension",
        module=module,
        install_kind=None,
        install_path=None,
        include_dirs=(),
        defines=(),
        flags=(),
        env={},
        depends_on=(),
    )


# ── _lib_filename ────────────────────────────────────────────────────────────


def test_lib_filename_linux() -> None:
    with patch.object(sys, "platform", "linux"):
        assert _lib_filename("Foo") == "libFoo.so"


def test_lib_filename_darwin() -> None:
    with patch.object(sys, "platform", "darwin"):
        assert _lib_filename("Foo") == "libFoo.dylib"


# ── discover_modular_lib ────────────────────────────────────────────────────


def test_discover_from_env_var(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    lib_dir = _make_modular_lib(tmp_path / "modular")
    monkeypatch.setenv("MODULAR_LIB_DIR", str(lib_dir))
    assert discover_modular_lib(tmp_path, None) == lib_dir


def test_discover_from_importlib(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    modular_dir = tmp_path / "modular"
    lib_dir = _make_modular_lib(modular_dir)
    monkeypatch.delenv("MODULAR_LIB_DIR", raising=False)

    fake_spec = SimpleNamespace(origin=str(modular_dir / "__init__.py"))
    monkeypatch.setattr("hatch_mojo.runtime.importlib.util.find_spec", lambda _name: fake_spec)
    assert discover_modular_lib(tmp_path, None) == lib_dir


def test_discover_from_mojo_binary(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # modular/bin/mojo → modular/lib/
    modular = tmp_path / "modular"
    lib_dir = _make_modular_lib(modular)
    bin_dir = modular / "bin"
    bin_dir.mkdir(parents=True)
    mojo_bin = bin_dir / "mojo"
    mojo_bin.write_bytes(b"")

    monkeypatch.delenv("MODULAR_LIB_DIR", raising=False)
    monkeypatch.setattr("hatch_mojo.runtime.importlib.util.find_spec", lambda _name: None)
    assert discover_modular_lib(tmp_path, str(mojo_bin)) == lib_dir


def test_discover_from_container_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    lib_dir = _make_modular_lib(tmp_path / ".modular")
    monkeypatch.delenv("MODULAR_LIB_DIR", raising=False)
    monkeypatch.setattr("hatch_mojo.runtime.importlib.util.find_spec", lambda _name: None)
    assert discover_modular_lib(tmp_path, None) == lib_dir


def test_discover_not_found(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MODULAR_LIB_DIR", raising=False)
    monkeypatch.setattr("hatch_mojo.runtime.importlib.util.find_spec", lambda _name: None)
    with pytest.raises(FileNotFoundError, match="Could not locate Mojo runtime"):
        discover_modular_lib(tmp_path, None)


def test_discover_env_var_missing_sentinel(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Env var pointing to a dir without the sentinel is skipped."""
    lib_dir = tmp_path / "fake" / "lib"
    lib_dir.mkdir(parents=True)
    monkeypatch.setenv("MODULAR_LIB_DIR", str(lib_dir))
    monkeypatch.setattr("hatch_mojo.runtime.importlib.util.find_spec", lambda _name: None)
    with pytest.raises(FileNotFoundError):
        discover_modular_lib(tmp_path, None)


# ── _compute_extension_rpath ────────────────────────────────────────────────


def test_rpath_depth_1_linux() -> None:
    with patch.object(sys, "platform", "linux"):
        result = _compute_extension_rpath("mogemma._core", "mogemma")
        assert result == "$ORIGIN:$ORIGIN/../mogemma.libs"


def test_rpath_depth_2_linux() -> None:
    with patch.object(sys, "platform", "linux"):
        result = _compute_extension_rpath("pkg.sub._core", "pkg")
        assert result == "$ORIGIN:$ORIGIN/../../pkg.libs"


def test_rpath_depth_1_darwin() -> None:
    with patch.object(sys, "platform", "darwin"):
        result = _compute_extension_rpath("mogemma._core", "mogemma")
        assert result == "@loader_path:@loader_path/../mogemma.libs"


def test_rpath_depth_3() -> None:
    with patch.object(sys, "platform", "linux"):
        result = _compute_extension_rpath("a.b.c._core", "a")
        assert result == "$ORIGIN:$ORIGIN/../../../a.libs"


# ── _patch_rpath ─────────────────────────────────────────────────────────────


def test_patch_rpath_linux(tmp_path: Path) -> None:
    target = tmp_path / "lib.so"
    target.write_bytes(b"")
    with (
        patch.object(sys, "platform", "linux"),
        patch("hatch_mojo.runtime.subprocess.run") as mock_run,
    ):
        _patch_rpath(target, "$ORIGIN")
        mock_run.assert_called_once_with(
            ["patchelf", "--set-rpath", "$ORIGIN", str(target)],
            check=True,
            capture_output=True,
        )


def test_patch_rpath_darwin(tmp_path: Path) -> None:
    target = tmp_path / "lib.dylib"
    target.write_bytes(b"")
    with (
        patch.object(sys, "platform", "darwin"),
        patch("hatch_mojo.runtime.subprocess.run") as mock_run,
    ):
        _patch_rpath(target, "@loader_path")
        mock_run.assert_called_once_with(
            ["install_name_tool", "-add_rpath", "@loader_path", str(target)],
            check=True,
            capture_output=True,
        )


def test_patch_rpath_windows_noop(tmp_path: Path) -> None:
    target = tmp_path / "lib.dll"
    target.write_bytes(b"")
    with (
        patch.object(sys, "platform", "win32"),
        patch("hatch_mojo.runtime.subprocess.run") as mock_run,
    ):
        _patch_rpath(target, "anything")
        mock_run.assert_not_called()


# ── bundle_runtime_libs ─────────────────────────────────────────────────────


def test_bundle_skips_on_windows(tmp_path: Path) -> None:
    with patch.object(sys, "platform", "win32"):
        result = bundle_runtime_libs(tmp_path, "build/mojo", [], None)
        assert result == {}


def test_bundle_skips_no_ext_jobs(tmp_path: Path) -> None:
    non_ext = BuildJob(
        name="lib",
        input_path=tmp_path / "lib.mojo",
        output_path=tmp_path / "lib.so",
        emit="shared-lib",
        module=None,
        install_kind="force-include",
        install_path="lib/",
        include_dirs=(),
        defines=(),
        flags=(),
        env={},
        depends_on=(),
    )
    result = bundle_runtime_libs(tmp_path, "build/mojo", [non_ext], None)
    assert result == {}


def test_bundle_full_flow(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    modular = tmp_path / "modular"
    _make_modular_lib(modular)
    lib_dir = modular / "lib"
    monkeypatch.setenv("MODULAR_LIB_DIR", str(lib_dir))

    job = _ext_job(tmp_path, module="mogemma._core")

    with (
        patch.object(sys, "platform", "linux"),
        patch("hatch_mojo.runtime.subprocess.run"),
    ):
        result = bundle_runtime_libs(tmp_path, "build/mojo", [job], None)

    assert len(result) == len(_RUNTIME_LIB_BASES)
    libs_dir = tmp_path / "build" / "mojo" / "mogemma.libs"
    assert libs_dir.is_dir()

    for base in _RUNTIME_LIB_BASES:
        filename = f"lib{base}.so"
        assert (libs_dir / filename).exists()
        assert any(v == f"mogemma.libs/{filename}" for v in result.values())


def test_bundle_multiple_packages(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    modular = tmp_path / "modular"
    _make_modular_lib(modular)
    monkeypatch.setenv("MODULAR_LIB_DIR", str(modular / "lib"))

    job_a = _ext_job(tmp_path, module="pkga._core", name="a")
    job_b = _ext_job(tmp_path, module="pkgb._core", name="b")

    with (
        patch.object(sys, "platform", "linux"),
        patch("hatch_mojo.runtime.subprocess.run"),
    ):
        result = bundle_runtime_libs(tmp_path, "build/mojo", [job_a, job_b], None)

    assert len(result) == len(_RUNTIME_LIB_BASES) * 2
    assert any("pkga.libs/" in v for v in result.values())
    assert any("pkgb.libs/" in v for v in result.values())


def test_bundle_raises_on_missing_runtime_lib(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """If a runtime lib is missing from modular/lib, raise immediately."""
    lib_dir = tmp_path / "modular" / "lib"
    lib_dir.mkdir(parents=True)
    # Create sentinel + only the first lib, but omit the rest
    (lib_dir / _sentinel()).write_bytes(b"")
    (lib_dir / _lib_filename(_RUNTIME_LIB_BASES[0])).write_bytes(b"fake")
    monkeypatch.setenv("MODULAR_LIB_DIR", str(lib_dir))

    job = _ext_job(tmp_path)

    with (
        patch.object(sys, "platform", "linux"),
        patch("hatch_mojo.runtime.subprocess.run"),
        pytest.raises(FileNotFoundError, match="Missing required Mojo runtime"),
    ):
        bundle_runtime_libs(tmp_path, "build/mojo", [job], None)


# ── discover_modular_lib: namespace packages ────────────────────────────────


def test_discover_from_namespace_package(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Namespace package: spec.origin is None, submodule_search_locations has the path."""
    modular_dir = tmp_path / "modular"
    lib_dir = _make_modular_lib(modular_dir)
    monkeypatch.delenv("MODULAR_LIB_DIR", raising=False)

    fake_spec = SimpleNamespace(
        origin=None,
        submodule_search_locations=[str(modular_dir)],
    )
    monkeypatch.setattr("hatch_mojo.runtime.importlib.util.find_spec", lambda _name: fake_spec)
    assert discover_modular_lib(tmp_path, None) == lib_dir


def test_discover_namespace_package_skips_bad_locations(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Falls through when namespace locations lack the sentinel file."""
    bad_dir = tmp_path / "wrong"
    bad_dir.mkdir()
    monkeypatch.delenv("MODULAR_LIB_DIR", raising=False)

    fake_spec = SimpleNamespace(
        origin=None,
        submodule_search_locations=[str(bad_dir)],
    )
    monkeypatch.setattr("hatch_mojo.runtime.importlib.util.find_spec", lambda _name: fake_spec)
    with pytest.raises(FileNotFoundError):
        discover_modular_lib(tmp_path, None)


# ── _get_linked_libraries ──────────────────────────────────────────────────


def test_get_linked_libraries_parses_otool_output(tmp_path: Path) -> None:
    otool_output = (
        "/path/to/_core.so:\n"
        "\t/opt/modular/lib/libKGENCompilerRTShared.dylib (compatibility version 0.0.0)\n"
        "\t/opt/modular/lib/libAsyncRTRuntimeGlobals.dylib (compatibility version 0.0.0)\n"
        "\t/usr/lib/libSystem.B.dylib (compatibility version 1.0.0)\n"
    )
    mock_result = SimpleNamespace(stdout=otool_output)
    target = tmp_path / "test.dylib"
    target.write_bytes(b"")
    with patch("hatch_mojo.runtime.subprocess.run", return_value=mock_result):
        libs = _get_linked_libraries(target)
    assert libs == [
        "/opt/modular/lib/libKGENCompilerRTShared.dylib",
        "/opt/modular/lib/libAsyncRTRuntimeGlobals.dylib",
        "/usr/lib/libSystem.B.dylib",
    ]


def test_get_linked_libraries_handles_empty_deps(tmp_path: Path) -> None:
    otool_output = "/path/to/binary:\n"
    mock_result = SimpleNamespace(stdout=otool_output)
    target = tmp_path / "test.dylib"
    target.write_bytes(b"")
    with patch("hatch_mojo.runtime.subprocess.run", return_value=mock_result):
        libs = _get_linked_libraries(target)
    assert libs == []


# ── _strip_absolute_rpaths ──────────────────────────────────────────────────


_OTOOL_LOAD_COMMANDS = (
    "Load command 0\n"
    "      cmd LC_RPATH\n"
    "  cmdsize 40\n"
    "    path /opt/modular/lib (offset 12)\n"
    "Load command 1\n"
    "      cmd LC_RPATH\n"
    "  cmdsize 48\n"
    "    path @loader_path/../lib (offset 12)\n"
    "Load command 2\n"
    "      cmd LC_RPATH\n"
    "  cmdsize 40\n"
    "    path /usr/local/lib (offset 12)\n"
    "Load command 3\n"
    "      cmd LC_RPATH\n"
    "  cmdsize 48\n"
    "    path @rpath/more (offset 12)\n"
)


def test_strip_absolute_rpaths(tmp_path: Path) -> None:
    """Only absolute RPATHs are deleted; @-prefixed ones are kept."""
    target = tmp_path / "lib.dylib"
    target.write_bytes(b"")
    mock_result = SimpleNamespace(stdout=_OTOOL_LOAD_COMMANDS)

    with patch("hatch_mojo.runtime.subprocess.run", return_value=mock_result) as mock_run:
        _strip_absolute_rpaths(target)

    calls = mock_run.call_args_list
    # First call: otool -l
    assert calls[0].args[0] == ["otool", "-l", str(target)]
    # Two delete_rpath calls for the absolute paths
    assert calls[1].args[0] == [
        "install_name_tool",
        "-delete_rpath",
        "/opt/modular/lib",
        str(target),
    ]
    assert calls[2].args[0] == [
        "install_name_tool",
        "-delete_rpath",
        "/usr/local/lib",
        str(target),
    ]
    # No more calls — @loader_path and @rpath entries are preserved
    assert len(calls) == 3


def test_strip_absolute_rpaths_preserves_at_paths(tmp_path: Path) -> None:
    """When all RPATHs start with @, no delete_rpath calls are made."""
    otool_output = (
        "Load command 0\n"
        "      cmd LC_RPATH\n"
        "  cmdsize 48\n"
        "    path @loader_path/../lib (offset 12)\n"
        "Load command 1\n"
        "      cmd LC_RPATH\n"
        "  cmdsize 40\n"
        "    path @rpath/more (offset 12)\n"
    )
    target = tmp_path / "lib.dylib"
    target.write_bytes(b"")
    mock_result = SimpleNamespace(stdout=otool_output)

    with patch("hatch_mojo.runtime.subprocess.run", return_value=mock_result) as mock_run:
        _strip_absolute_rpaths(target)

    # Only the otool -l call, no delete_rpath calls
    assert len(mock_run.call_args_list) == 1


# ── _has_rpath ──────────────────────────────────────────────────────────────


def test_has_rpath_true(tmp_path: Path) -> None:
    target = tmp_path / "ext.so"
    target.write_bytes(b"")
    mock_result = SimpleNamespace(stdout=_OTOOL_LOAD_COMMANDS)

    with patch("hatch_mojo.runtime.subprocess.run", return_value=mock_result):
        assert _has_rpath(target, "/opt/modular/lib") is True


def test_has_rpath_false(tmp_path: Path) -> None:
    target = tmp_path / "ext.so"
    target.write_bytes(b"")
    mock_result = SimpleNamespace(stdout=_OTOOL_LOAD_COMMANDS)

    with patch("hatch_mojo.runtime.subprocess.run", return_value=mock_result):
        assert _has_rpath(target, "/nonexistent/path") is False


# ── _patch_macos_dylibs ────────────────────────────────────────────────────


def test_patch_macos_dylibs_changes_id(tmp_path: Path) -> None:
    """Verifies -id @rpath/<filename> is called, then ad-hoc re-signed."""
    libs_dir = tmp_path / "libs"
    libs_dir.mkdir()
    (libs_dir / "libFoo.dylib").write_bytes(b"")

    # _get_linked_libraries returns no deps so only -id + codesign are called
    with (
        patch("hatch_mojo.runtime.subprocess.run") as mock_run,
        patch("hatch_mojo.runtime._get_linked_libraries", return_value=[]),
        patch("hatch_mojo.runtime._strip_absolute_rpaths"),
    ):
        _patch_macos_dylibs(libs_dir, ["libFoo.dylib"])

    calls = mock_run.call_args_list
    assert len(calls) == 2
    assert calls[0].args[0] == [
        "install_name_tool",
        "-id",
        "@rpath/libFoo.dylib",
        str(libs_dir / "libFoo.dylib"),
    ]
    assert calls[1].args[0] == [
        "codesign",
        "-s",
        "-",
        "-f",
        str(libs_dir / "libFoo.dylib"),
    ]


def test_patch_macos_dylibs_fixes_sibling_references(tmp_path: Path) -> None:
    """Verifies -change for inter-library references between siblings."""
    libs_dir = tmp_path / "libs"
    libs_dir.mkdir()
    (libs_dir / "libA.dylib").write_bytes(b"")

    linked = ["/opt/modular/lib/libB.dylib"]

    with (
        patch("hatch_mojo.runtime.subprocess.run") as mock_run,
        patch("hatch_mojo.runtime._get_linked_libraries", return_value=linked),
        patch("hatch_mojo.runtime._strip_absolute_rpaths"),
    ):
        _patch_macos_dylibs(libs_dir, ["libA.dylib", "libB.dylib"])

    calls = mock_run.call_args_list
    # -id for libA
    assert calls[0].args[0] == [
        "install_name_tool",
        "-id",
        "@rpath/libA.dylib",
        str(libs_dir / "libA.dylib"),
    ]
    # -change for libB reference
    assert calls[1].args[0] == [
        "install_name_tool",
        "-change",
        "/opt/modular/lib/libB.dylib",
        "@rpath/libB.dylib",
        str(libs_dir / "libA.dylib"),
    ]
    # codesign for libA
    assert calls[2].args[0] == [
        "codesign",
        "-s",
        "-",
        "-f",
        str(libs_dir / "libA.dylib"),
    ]


def test_patch_macos_dylibs_ignores_system_libs(tmp_path: Path) -> None:
    """System libs (/usr/lib/..., /System/...) are not rewritten."""
    libs_dir = tmp_path / "libs"
    libs_dir.mkdir()
    (libs_dir / "libFoo.dylib").write_bytes(b"")

    linked = ["/usr/lib/libSystem.B.dylib", "/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation"]

    with (
        patch("hatch_mojo.runtime.subprocess.run") as mock_run,
        patch("hatch_mojo.runtime._get_linked_libraries", return_value=linked),
        patch("hatch_mojo.runtime._strip_absolute_rpaths"),
    ):
        _patch_macos_dylibs(libs_dir, ["libFoo.dylib"])

    # -id call + codesign, no -change calls for system libs
    assert mock_run.call_count == 2
    assert calls_contain_flag(mock_run.call_args_list, "-id")
    assert calls_contain_flag(mock_run.call_args_list, "codesign")


def test_patch_macos_extension_rewrites_refs_and_adds_rpath(tmp_path: Path) -> None:
    """Full extension patching: -change for bundled libs, then -add_rpath."""
    ext = tmp_path / "_core.so"
    ext.write_bytes(b"")
    linked = [
        "/opt/modular/lib/libKGENCompilerRTShared.dylib",
        "/usr/lib/libSystem.B.dylib",
    ]
    lib_filenames = ["libKGENCompilerRTShared.dylib", "libAsyncRTRuntimeGlobals.dylib"]
    rpath = "@loader_path:@loader_path/../mogemma.libs"

    with (
        patch("hatch_mojo.runtime.subprocess.run") as mock_run,
        patch("hatch_mojo.runtime._get_linked_libraries", return_value=linked),
        patch("hatch_mojo.runtime._has_rpath", return_value=False),
    ):
        _patch_macos_extension(ext, lib_filenames, rpath)

    calls = mock_run.call_args_list
    # -change for the modular lib
    assert calls[0].args[0] == [
        "install_name_tool",
        "-change",
        "/opt/modular/lib/libKGENCompilerRTShared.dylib",
        "@rpath/libKGENCompilerRTShared.dylib",
        str(ext),
    ]
    # -add_rpath
    assert calls[1].args[0] == [
        "install_name_tool",
        "-add_rpath",
        rpath,
        str(ext),
    ]
    # codesign
    assert calls[2].args[0] == [
        "codesign",
        "-s",
        "-",
        "-f",
        str(ext),
    ]


def test_patch_macos_extension_skips_existing_rpath(tmp_path: Path) -> None:
    """When the rpath already exists, -add_rpath is not called."""
    ext = tmp_path / "_core.so"
    ext.write_bytes(b"")
    rpath = "@loader_path:@loader_path/../mogemma.libs"

    with (
        patch("hatch_mojo.runtime.subprocess.run") as mock_run,
        patch("hatch_mojo.runtime._get_linked_libraries", return_value=[]),
        patch("hatch_mojo.runtime._has_rpath", return_value=True),
    ):
        _patch_macos_extension(ext, ["libFoo.dylib"], rpath)

    # Only codesign should be called — no -add_rpath
    assert mock_run.call_count == 1
    assert mock_run.call_args_list[0].args[0] == [
        "codesign",
        "-s",
        "-",
        "-f",
        str(ext),
    ]


# ── _resign_ad_hoc ─────────────────────────────────────────────────────────


def test_resign_ad_hoc(tmp_path: Path) -> None:
    target = tmp_path / "lib.dylib"
    target.write_bytes(b"")
    with patch("hatch_mojo.runtime.subprocess.run") as mock_run:
        _resign_ad_hoc(target)
    mock_run.assert_called_once_with(
        ["codesign", "-s", "-", "-f", str(target)],
        check=True,
        capture_output=True,
    )


# ── bundle_runtime_libs: write permissions ─────────────────────────────────


def test_bundle_ensures_writable_copies(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Copied libs must be writable even if source is read-only."""
    modular = tmp_path / "modular"
    _make_modular_lib(modular)
    lib_dir = modular / "lib"
    # Make source libs read-only
    for f in lib_dir.iterdir():
        f.chmod(stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH)
    monkeypatch.setenv("MODULAR_LIB_DIR", str(lib_dir))

    job = _ext_job(tmp_path, module="mogemma._core")

    with (
        patch.object(sys, "platform", "linux"),
        patch("hatch_mojo.runtime.subprocess.run"),
    ):
        bundle_runtime_libs(tmp_path, "build/mojo", [job], None)

    libs_dir = tmp_path / "build" / "mojo" / "mogemma.libs"
    for f in libs_dir.iterdir():
        assert f.stat().st_mode & stat.S_IWUSR, f"{f.name} should be writable"


# ── bundle_runtime_libs: macOS full flow ───────────────────────────────────


def test_bundle_full_flow_darwin(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """End-to-end macOS bundling with mocked subprocess."""
    # Mock otool to return empty deps (simplifies assertions)
    mock_result = SimpleNamespace(stdout="/path/to/lib:\n")
    with (
        patch.object(sys, "platform", "darwin"),
        patch("hatch_mojo.runtime.subprocess.run", return_value=mock_result),
    ):
        # Create modular lib dir inside mock so _sentinel() returns .dylib
        modular = tmp_path / "modular"
        _make_modular_lib(modular)
        lib_dir = modular / "lib"
        monkeypatch.setenv("MODULAR_LIB_DIR", str(lib_dir))

        job = _ext_job(tmp_path, module="mogemma._core")
        result = bundle_runtime_libs(tmp_path, "build/mojo", [job], None)

    assert len(result) == len(_RUNTIME_LIB_BASES)
    libs_dir = tmp_path / "build" / "mojo" / "mogemma.libs"
    assert libs_dir.is_dir()

    for base in _RUNTIME_LIB_BASES:
        filename = f"lib{base}.dylib"
        assert (libs_dir / filename).exists()
        assert any(v == f"mogemma.libs/{filename}" for v in result.values())


# ── test helpers ───────────────────────────────────────────────────────────


def calls_contain_flag(call_list: Any, flag: str) -> bool:
    """Check if any call in a mock's call_args_list contains the given flag."""
    return any(flag in call.args[0] for call in call_list)
