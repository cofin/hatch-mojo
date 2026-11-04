from __future__ import annotations

import stat
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import call, patch

import pytest

from hatch_mojo.runtime import (
    _compute_extension_rpath,
    _get_linked_libraries,
    _lib_filename,
    _patch_macos_dylibs,
    _patch_macos_extension,
    _patch_rpath,
    _resign_ad_hoc,
    _resolve_modular_dependencies,
    _run_install_name_tool,
    _sentinel,
    _strip_absolute_rpaths,
    _write_license_notice,
    bundle_runtime_libs,
    discover_modular_lib,
    patch_editable_runtime,
)
from hatch_mojo.types import BuildJob, RuntimeBundleResult

# ── helpers ──────────────────────────────────────────────────────────────────


def _make_modular_lib(base: Path) -> Path:
    """Create a fake modular/lib directory with the sentinel and all runtime libs."""
    lib_dir = base / "lib"
    lib_dir.mkdir(parents=True, exist_ok=True)
    (lib_dir / _sentinel()).write_bytes(b"")
    for name in ["KGENCompilerRTShared", "AsyncRTRuntimeGlobals", "MSupportGlobals"]:
        (lib_dir / _lib_filename(name)).write_bytes(b"fake")
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


def _isolate_ambient_sdk(monkeypatch: pytest.MonkeyPatch) -> None:
    """Clear ambient SDK environment variables and package-root modules for fallback tests."""
    monkeypatch.delenv("MODULAR_LIB_DIR", raising=False)
    monkeypatch.delenv("CONDA_PREFIX", raising=False)
    monkeypatch.setitem(sys.modules, "mojo", None)
    monkeypatch.setitem(sys.modules, "mojo._package_root", None)


def test_discover_from_env_var(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    lib_dir = _make_modular_lib(tmp_path / "modular")
    monkeypatch.setenv("MODULAR_LIB_DIR", str(lib_dir))
    assert discover_modular_lib(tmp_path, None) == lib_dir


def test_discover_from_importlib(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    modular_dir = tmp_path / "modular"
    lib_dir = _make_modular_lib(modular_dir)
    _isolate_ambient_sdk(monkeypatch)

    fake_spec = SimpleNamespace(origin=str(modular_dir / "__init__.py"), submodule_search_locations=None)
    monkeypatch.setattr(
        "hatch_mojo.runtime.importlib.util.find_spec",
        lambda name: fake_spec if name == "modular" else None,
    )
    assert discover_modular_lib(tmp_path, None) == lib_dir


def test_discover_from_mojo_package_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _isolate_ambient_sdk(monkeypatch)
    monkeypatch.setattr("hatch_mojo.runtime.importlib.util.find_spec", lambda _name: None)

    sdk = tmp_path / "pkg_sdk"
    lib_dir = _make_modular_lib(sdk)
    fake_pkg_root = SimpleNamespace(get_package_root=lambda: str(sdk))
    monkeypatch.setitem(sys.modules, "mojo", SimpleNamespace())
    monkeypatch.setitem(sys.modules, "mojo._package_root", fake_pkg_root)
    assert discover_modular_lib(tmp_path, None) == lib_dir

    fallback_lib = _make_modular_lib(tmp_path / ".modular")
    monkeypatch.setitem(sys.modules, "mojo._package_root", SimpleNamespace(get_package_root=lambda: None))
    assert discover_modular_lib(tmp_path, None) == fallback_lib


def test_discover_mojo_bin_wins_over_ambient_package_root(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _isolate_ambient_sdk(monkeypatch)
    monkeypatch.setattr("hatch_mojo.runtime.importlib.util.find_spec", lambda _name: None)

    ambient_sdk = tmp_path / "ambient_sdk"
    _make_modular_lib(ambient_sdk)
    monkeypatch.setitem(sys.modules, "mojo", SimpleNamespace())
    monkeypatch.setitem(
        sys.modules,
        "mojo._package_root",
        SimpleNamespace(get_package_root=lambda: str(ambient_sdk)),
    )

    explicit_sdk = tmp_path / "explicit_sdk"
    explicit_lib = _make_modular_lib(explicit_sdk)
    mojo_bin = explicit_sdk / "bin" / "mojo"
    mojo_bin.parent.mkdir(parents=True)
    mojo_bin.write_bytes(b"")

    assert discover_modular_lib(tmp_path, str(mojo_bin)) == explicit_lib


def test_discover_from_mojo_spec_sibling_modular_lib(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _isolate_ambient_sdk(monkeypatch)
    site_packages = tmp_path / "venv" / "lib" / "python3.12" / "site-packages"
    mojo_pkg = site_packages / "mojo"
    mojo_pkg.mkdir(parents=True)
    origin_init = mojo_pkg / "__init__.py"
    origin_init.write_text("", encoding="utf-8")

    sibling_lib = _make_modular_lib(site_packages / "modular")
    fake_spec = SimpleNamespace(origin=str(origin_init), submodule_search_locations=[str(mojo_pkg)])
    monkeypatch.setattr(
        "hatch_mojo.runtime.importlib.util.find_spec",
        lambda name: fake_spec if name == "mojo" else None,
    )
    assert discover_modular_lib(tmp_path, None) == sibling_lib


@pytest.mark.parametrize(
    "site_rel",
    [
        "lib/python3.12/site-packages/modular",
        "lib64/python3.12/site-packages/modular",
        "lib/python3.12/dist-packages/modular",
        "Lib/site-packages/modular",
    ],
)
def test_discover_from_external_wrapper_venv_layouts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    site_rel: str,
) -> None:
    _isolate_ambient_sdk(monkeypatch)
    monkeypatch.setattr("hatch_mojo.runtime.importlib.util.find_spec", lambda _name: None)

    tool_venv = tmp_path / "tool-venv"
    mojo_wrapper = tool_venv / "bin" / "mojo"
    mojo_wrapper.parent.mkdir(parents=True)
    mojo_wrapper.write_text("#!/usr/bin/env python3\n", encoding="utf-8")
    expected_lib = _make_modular_lib(tool_venv / site_rel)

    assert discover_modular_lib(tmp_path, str(mojo_wrapper)) == expected_lib

    monkeypatch.setattr(
        "hatch_mojo.runtime.shutil.which",
        lambda name: str(mojo_wrapper) if name == "mojo" else None,
    )
    assert discover_modular_lib(tmp_path, "mojo") == expected_lib


def test_discover_from_conda_prefix_and_pixi(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _isolate_ambient_sdk(monkeypatch)
    monkeypatch.setattr("hatch_mojo.runtime.importlib.util.find_spec", lambda _name: None)

    pixi_lib = _make_modular_lib(tmp_path / ".pixi" / "envs" / "default")
    assert discover_modular_lib(tmp_path, None) == pixi_lib

    conda_prefix = tmp_path / "conda_env"
    conda_lib = _make_modular_lib(conda_prefix)
    monkeypatch.setenv("CONDA_PREFIX", str(conda_prefix))
    assert discover_modular_lib(tmp_path, None) == conda_lib


def test_discover_from_mojo_binary(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    modular = tmp_path / "modular"
    lib_dir = _make_modular_lib(modular)
    bin_dir = modular / "bin"
    bin_dir.mkdir(parents=True)
    mojo_bin = bin_dir / "mojo"
    mojo_bin.write_bytes(b"")

    _isolate_ambient_sdk(monkeypatch)
    monkeypatch.setattr("hatch_mojo.runtime.importlib.util.find_spec", lambda _name: None)
    assert discover_modular_lib(tmp_path, str(mojo_bin)) == lib_dir


def test_discover_from_container_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    lib_dir = _make_modular_lib(tmp_path / ".modular")
    _isolate_ambient_sdk(monkeypatch)
    monkeypatch.setattr("hatch_mojo.runtime.importlib.util.find_spec", lambda _name: None)
    assert discover_modular_lib(tmp_path, None) == lib_dir


def test_discover_not_found(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _isolate_ambient_sdk(monkeypatch)
    monkeypatch.setattr("hatch_mojo.runtime.importlib.util.find_spec", lambda _name: None)
    with pytest.raises(FileNotFoundError, match=r"mojo-compiler>=1\.2\.0.*MODULAR_LIB_DIR"):
        discover_modular_lib(tmp_path, None)


def test_discover_env_var_missing_sentinel(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Env var pointing to a dir without the sentinel is skipped."""
    lib_dir = tmp_path / "fake" / "lib"
    lib_dir.mkdir(parents=True)
    _isolate_ambient_sdk(monkeypatch)
    monkeypatch.setenv("MODULAR_LIB_DIR", str(lib_dir))
    monkeypatch.setattr("hatch_mojo.runtime.importlib.util.find_spec", lambda _name: None)
    with pytest.raises(FileNotFoundError):
        discover_modular_lib(tmp_path, None)


# ── _compute_extension_rpath ────────────────────────────────────────────────


def test_rpath_depth_0_linux() -> None:
    with patch.object(sys, "platform", "linux"):
        result = _compute_extension_rpath("_core", "_core")
        assert result == ["$ORIGIN", "$ORIGIN/_core.libs"]


def test_rpath_depth_0_darwin() -> None:
    with patch.object(sys, "platform", "darwin"):
        result = _compute_extension_rpath("_core", "_core")
        assert result == ["@loader_path", "@loader_path/_core.libs"]


def test_rpath_depth_1_linux() -> None:
    with patch.object(sys, "platform", "linux"):
        result = _compute_extension_rpath("mogemma._core", "mogemma")
        assert result == ["$ORIGIN", "$ORIGIN/../mogemma.libs"]


def test_rpath_depth_2_linux() -> None:
    with patch.object(sys, "platform", "linux"):
        result = _compute_extension_rpath("pkg.sub._core", "pkg")
        assert result == ["$ORIGIN", "$ORIGIN/../../pkg.libs"]


def test_rpath_depth_1_darwin() -> None:
    with patch.object(sys, "platform", "darwin"):
        result = _compute_extension_rpath("mogemma._core", "mogemma")
        assert result == ["@loader_path", "@loader_path/../mogemma.libs"]


def test_rpath_depth_3() -> None:
    with patch.object(sys, "platform", "linux"):
        result = _compute_extension_rpath("a.b.c._core", "a")
        assert result == ["$ORIGIN", "$ORIGIN/../../../a.libs"]


# ── _patch_rpath ─────────────────────────────────────────────────────────────


def test_patch_rpath_linux(tmp_path: Path) -> None:
    target = tmp_path / "lib.so"
    target.write_bytes(b"")
    with (
        patch.object(sys, "platform", "linux"),
        patch("hatch_mojo.runtime.subprocess.run") as mock_run,
    ):
        _patch_rpath(target, ["$ORIGIN"])
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
        _patch_rpath(target, ["@loader_path", "@loader_path/../pkg.libs"])
        assert mock_run.call_args_list == [
            call(
                ["install_name_tool", "-add_rpath", "@loader_path", str(target)],
                check=True,
                capture_output=True,
                text=True,
            ),
            call(
                ["install_name_tool", "-add_rpath", "@loader_path/../pkg.libs", str(target)],
                check=True,
                capture_output=True,
                text=True,
            ),
            call(
                ["codesign", "-s", "-", "-f", str(target)],
                check=True,
                capture_output=True,
            ),
        ]


def test_patch_rpath_windows_noop(tmp_path: Path) -> None:
    target = tmp_path / "lib.dll"
    target.write_bytes(b"")
    with (
        patch.object(sys, "platform", "win32"),
        patch("hatch_mojo.runtime.subprocess.run") as mock_run,
    ):
        _patch_rpath(target, ["anything"])
        mock_run.assert_not_called()


# ── bundle_runtime_libs ─────────────────────────────────────────────────────


def test_bundle_skips_on_windows(tmp_path: Path) -> None:
    with patch.object(sys, "platform", "win32"):
        result = bundle_runtime_libs(tmp_path, "build/mojo", [], None)
        assert result == RuntimeBundleResult(force_include={}, shared_data={}, staged_files=())


def test_bundle_skips_no_ext_jobs(tmp_path: Path) -> None:
    obj_job = BuildJob(
        name="obj",
        input_path=tmp_path / "obj.mojo",
        output_path=tmp_path / "obj.o",
        emit="object",
        module=None,
        install_kind="force-include",
        install_path="lib/obj.o",
        include_dirs=(),
        defines=(),
        flags=(),
        env={},
        depends_on=(),
    )
    mojoc_job = BuildJob(
        name="pkg",
        input_path=tmp_path / "pkg.mojo",
        output_path=tmp_path / "pkg.mojoc",
        emit="mojoc",
        module=None,
        install_kind="package",
        install_path="mypkg",
        include_dirs=(),
        defines=(),
        flags=(),
        env={},
        depends_on=(),
    )
    result = bundle_runtime_libs(tmp_path, "build/mojo", [obj_job, mojoc_job], None)
    assert result == RuntimeBundleResult(force_include={}, shared_data={}, staged_files=())


def test_bundle_full_flow(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    modular = tmp_path / "modular"
    _make_modular_lib(modular)
    lib_dir = modular / "lib"
    monkeypatch.setenv("MODULAR_LIB_DIR", str(lib_dir))

    job = _ext_job(tmp_path, module="mogemma._core")

    def mock_resolve(target: Path, modular_lib: Path) -> set[str]:
        return {"libKGENCompilerRTShared.so", "libAsyncRTRuntimeGlobals.so", "libMSupportGlobals.so"}

    with (
        patch.object(sys, "platform", "linux"),
        patch("hatch_mojo.runtime.subprocess.run"),
        patch("hatch_mojo.runtime._resolve_modular_dependencies", side_effect=mock_resolve),
    ):
        result = bundle_runtime_libs(tmp_path, "build/mojo", [job], None)

    assert len(result.force_include) == 4
    assert result.shared_data == {}
    assert len(result.staged_files) == 4
    libs_dir = tmp_path / "build" / "mojo" / "mogemma.libs"
    assert libs_dir.is_dir()

    for base in ["KGENCompilerRTShared", "AsyncRTRuntimeGlobals", "MSupportGlobals"]:
        filename = f"lib{base}.so"
        assert (libs_dir / filename).exists()
        assert any(v == f"mogemma.libs/{filename}" for v in result.force_include.values())


def test_bundle_multiple_packages(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    modular = tmp_path / "modular"
    _make_modular_lib(modular)
    monkeypatch.setenv("MODULAR_LIB_DIR", str(modular / "lib"))

    job_a = _ext_job(tmp_path, module="pkga._core", name="a")
    job_b = _ext_job(tmp_path, module="pkgb._core", name="b")

    def mock_resolve(target: Path, modular_lib: Path) -> set[str]:
        return {"libKGENCompilerRTShared.so", "libAsyncRTRuntimeGlobals.so", "libMSupportGlobals.so"}

    with (
        patch.object(sys, "platform", "linux"),
        patch("hatch_mojo.runtime.subprocess.run"),
        patch("hatch_mojo.runtime._resolve_modular_dependencies", side_effect=mock_resolve),
    ):
        result = bundle_runtime_libs(tmp_path, "build/mojo", [job_a, job_b], None)

    assert len(result.force_include) == 8
    assert len(result.staged_files) == 8
    assert any("pkga.libs/" in v for v in result.force_include.values())
    assert any("pkgb.libs/" in v for v in result.force_include.values())


def test_bundle_raises_on_missing_runtime_lib(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """If a discovered runtime lib is missing from modular/lib, raise immediately."""
    lib_dir = tmp_path / "modular" / "lib"
    lib_dir.mkdir(parents=True)
    # Create sentinel so discovery succeeds
    (lib_dir / _sentinel()).write_bytes(b"")
    monkeypatch.setenv("MODULAR_LIB_DIR", str(lib_dir))

    job = _ext_job(tmp_path)

    # Mock dynamic resolver to return a library that does not exist in modular/lib
    def mock_resolve(target: Path, modular_lib: Path) -> set[str]:
        return {"libMissing.so"}

    with (
        patch.object(sys, "platform", "linux"),
        patch("hatch_mojo.runtime.subprocess.run"),
        patch("hatch_mojo.runtime._resolve_modular_dependencies", side_effect=mock_resolve),
        pytest.raises(FileNotFoundError, match=r"Missing required Mojo runtime library: .*libMissing\.so"),
    ):
        bundle_runtime_libs(tmp_path, "build/mojo", [job], None)


# ── discover_modular_lib: namespace packages ────────────────────────────────


def test_discover_from_namespace_package(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Namespace package: spec.origin is None, submodule_search_locations has the path."""
    modular_dir = tmp_path / "modular"
    lib_dir = _make_modular_lib(modular_dir)
    _isolate_ambient_sdk(monkeypatch)

    fake_spec = SimpleNamespace(
        origin=None,
        submodule_search_locations=[str(modular_dir)],
    )
    monkeypatch.setattr(
        "hatch_mojo.runtime.importlib.util.find_spec",
        lambda name: fake_spec if name == "modular" else None,
    )
    assert discover_modular_lib(tmp_path, None) == lib_dir


def test_discover_namespace_package_skips_bad_locations(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Falls through when namespace locations lack the sentinel file."""
    bad_dir = tmp_path / "wrong"
    bad_dir.mkdir()
    _isolate_ambient_sdk(monkeypatch)

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
    with patch("sys.platform", "darwin"), patch("hatch_mojo.runtime.subprocess.run", return_value=mock_result):
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
    with patch("sys.platform", "darwin"), patch("hatch_mojo.runtime.subprocess.run", return_value=mock_result):
        libs = _get_linked_libraries(target)
    assert libs == []


def test_get_linked_libraries_parses_ldd_output(tmp_path: Path) -> None:
    ldd_output = (
        "\tlinux-vdso.so.1 (0x00007fffa)\n"
        "\tlibKGENCompilerRTShared.so => /opt/modular/lib/libKGENCompilerRTShared.so (0x00007fffb)\n"
        "\t/lib64/ld-linux-x86-64.so.2 (0x00007fffc)\n"
    )
    mock_result = SimpleNamespace(stdout=ldd_output)
    target = tmp_path / "test.so"
    target.write_bytes(b"")
    with patch("sys.platform", "linux"), patch("hatch_mojo.runtime.subprocess.run", return_value=mock_result):
        libs = _get_linked_libraries(target)
    assert libs == [
        "/opt/modular/lib/libKGENCompilerRTShared.so",
        "/lib64/ld-linux-x86-64.so.2",
    ]


def test_get_linked_libraries_ldd_not_found_soname(tmp_path: Path) -> None:
    ldd_output = (
        "\tlinux-vdso.so.1 (0x00007fffa)\n"
        "\tlibAsyncRTMojoBindings.so => not found\n"
        "\tlibKGENCompilerRTShared.so => /opt/modular/lib/libKGENCompilerRTShared.so (0x00007fffb)\n"
    )
    mock_result = SimpleNamespace(stdout=ldd_output)
    target = tmp_path / "test.so"
    target.write_bytes(b"")
    with patch("sys.platform", "linux"), patch("hatch_mojo.runtime.subprocess.run", return_value=mock_result):
        libs = _get_linked_libraries(target)
    assert libs == [
        "libAsyncRTMojoBindings.so",
        "/opt/modular/lib/libKGENCompilerRTShared.so",
    ]


def test_get_linked_libraries_raises_runtime_error_on_failure(tmp_path: Path) -> None:
    target = tmp_path / "test.so"
    target.write_bytes(b"")
    mock_err = subprocess.CalledProcessError(1, ["ldd", "test.so"], stderr="ldd: not found")
    with (
        patch("sys.platform", "linux"),
        patch("hatch_mojo.runtime.subprocess.run", side_effect=mock_err),
        pytest.raises(RuntimeError, match="Failed to resolve dependencies"),
    ):
        _get_linked_libraries(target)


# ── _resolve_modular_dependencies ──────────────────────────────────────────


def test_resolve_modular_dependencies_recursive(tmp_path: Path) -> None:
    modular_lib = tmp_path / "modular_lib"
    modular_lib.mkdir()
    (modular_lib / "libA.so").write_text("")
    (modular_lib / "libB.so").write_text("")
    (modular_lib / "libC.so").write_text("")

    entry = tmp_path / "entry.so"

    # Mock _get_linked_libraries to return different things based on the path
    def mock_get_linked_libraries(target: Path) -> list[str]:
        if target.name == "entry.so":
            return ["/opt/modular/lib/libA.so", "/usr/lib/libSystem.so"]
        if target.name == "libA.so":
            return ["/opt/modular/lib/libB.so"]
        if target.name == "libB.so":
            return ["/opt/modular/lib/libC.so"]
        if target.name == "libC.so":
            return []  # No more deps
        return []

    with patch("hatch_mojo.runtime._get_linked_libraries", side_effect=mock_get_linked_libraries):
        result = _resolve_modular_dependencies(entry, modular_lib)

    assert result == {"libA.so", "libB.so", "libC.so"}


def test_resolve_modular_dependencies_handles_cycles(tmp_path: Path) -> None:
    modular_lib = tmp_path / "modular_lib"
    modular_lib.mkdir()
    (modular_lib / "libA.so").write_text("")
    (modular_lib / "libB.so").write_text("")

    entry = tmp_path / "entry.so"

    def mock_get_linked_libraries(target: Path) -> list[str]:
        if target.name == "entry.so":
            return ["/opt/modular/lib/libA.so"]
        if target.name == "libA.so":
            return ["/opt/modular/lib/libB.so"]
        if target.name == "libB.so":
            return ["/opt/modular/lib/libA.so"]  # Cycle!
        return []

    with patch("hatch_mojo.runtime._get_linked_libraries", side_effect=mock_get_linked_libraries):
        result = _resolve_modular_dependencies(entry, modular_lib)

    assert result == {"libA.so", "libB.so"}


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


def test_strip_absolute_rpaths_ignores_non_lc_rpath_blocks(tmp_path: Path) -> None:
    """Lines with 'path ' inside non-LC_RPATH load commands must not trigger -delete_rpath."""
    otool_output = (
        "Load command 0\n"
        "      cmd LC_ID_DYLIB\n"
        "  cmdsize 56\n"
        "     name /opt/modular/lib/libFoo.dylib (offset 24)\n"
        "Load command 1\n"
        "      cmd LC_LOAD_DYLIB\n"
        "  cmdsize 56\n"
        "     path /usr/local/something (offset 24)\n"
        "Load command 2\n"
        "      cmd LC_RPATH\n"
        "  cmdsize 40\n"
        "     path /opt/modular/lib (offset 12)\n"
        "Load command 3\n"
        "      cmd LC_SYMTAB\n"
        "  cmdsize 24\n"
        "     path /tmp/ignored (offset 8)\n"
    )
    target = tmp_path / "lib.dylib"
    target.write_bytes(b"")
    mock_result = SimpleNamespace(stdout=otool_output)

    with patch("hatch_mojo.runtime.subprocess.run", return_value=mock_result) as mock_run:
        _strip_absolute_rpaths(target)

    calls = mock_run.call_args_list
    assert len(calls) == 2
    assert calls[0].args[0] == ["otool", "-l", str(target)]
    assert calls[1].args[0] == [
        "install_name_tool",
        "-delete_rpath",
        "/opt/modular/lib",
        str(target),
    ]


# ── _run_install_name_tool ───────────────────────────────────────────────────


def test_run_install_name_tool_success() -> None:
    with patch("hatch_mojo.runtime.subprocess.run") as mock_run:
        _run_install_name_tool(["-add_rpath", "foo", "bar"])
    mock_run.assert_called_once_with(
        ["install_name_tool", "-add_rpath", "foo", "bar"],
        check=True,
        capture_output=True,
        text=True,
    )


def test_run_install_name_tool_ignores_errors() -> None:
    err = subprocess.CalledProcessError(1, [], stderr="already contains LC_RPATH")
    with patch("hatch_mojo.runtime.subprocess.run", side_effect=err):
        _run_install_name_tool(["-add_rpath", "foo", "bar"], ignore_errors=["already contains LC_RPATH"])


def test_run_install_name_tool_raises_on_other_errors() -> None:
    err = subprocess.CalledProcessError(1, [], stderr="some random error")
    with (
        patch("hatch_mojo.runtime.subprocess.run", side_effect=err),
        pytest.raises(RuntimeError, match="some random error"),
    ):
        _run_install_name_tool(["-add_rpath", "foo", "bar"], ignore_errors=["already contains LC_RPATH"])


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
    """Full extension patching: strip absolute RPATHs, -change bundled libs, -add_rpath, codesign."""
    ext = tmp_path / "_core.so"
    ext.write_bytes(b"")
    linked = [
        "/opt/modular/lib/libKGENCompilerRTShared.dylib",
        "/usr/lib/libSystem.B.dylib",
    ]
    lib_filenames = ["libKGENCompilerRTShared.dylib", "libAsyncRTRuntimeGlobals.dylib"]
    rpaths = ["@loader_path", "@loader_path/../mogemma.libs"]

    with (
        patch("hatch_mojo.runtime.subprocess.run", return_value=SimpleNamespace(stdout="")) as mock_run,
        patch("hatch_mojo.runtime._get_linked_libraries", return_value=linked),
    ):
        _patch_macos_extension(ext, lib_filenames, rpaths)

    calls = mock_run.call_args_list
    assert calls[0].args[0] == ["otool", "-l", str(ext)]
    assert calls[1].args[0] == [
        "install_name_tool",
        "-change",
        "/opt/modular/lib/libKGENCompilerRTShared.dylib",
        "@rpath/libKGENCompilerRTShared.dylib",
        str(ext),
    ]
    assert calls[2].args[0] == [
        "install_name_tool",
        "-add_rpath",
        "@loader_path",
        str(ext),
    ]
    assert calls[3].args[0] == [
        "install_name_tool",
        "-add_rpath",
        "@loader_path/../mogemma.libs",
        str(ext),
    ]
    assert calls[4].args[0] == [
        "codesign",
        "-s",
        "-",
        "-f",
        str(ext),
    ]


def test_patch_macos_extension_strips_residual_absolute_rpaths(tmp_path: Path) -> None:
    """_patch_macos_extension deletes residual absolute LC_RPATH entries before adding @loader_path."""
    ext = tmp_path / "_core.so"
    ext.write_bytes(b"")
    otool_output = "Load command 0\n      cmd LC_RPATH\n  cmdsize 40\n    path /opt/modular/lib (offset 12)\n"

    with (
        patch("hatch_mojo.runtime.subprocess.run", return_value=SimpleNamespace(stdout=otool_output)) as mock_run,
        patch("hatch_mojo.runtime._get_linked_libraries", return_value=[]),
    ):
        _patch_macos_extension(ext, ["libFoo.dylib"], ["@loader_path", "@loader_path/../pkg.libs"])

    calls = [c.args[0] for c in mock_run.call_args_list]
    assert calls == [
        ["otool", "-l", str(ext)],
        ["install_name_tool", "-delete_rpath", "/opt/modular/lib", str(ext)],
        ["install_name_tool", "-add_rpath", "@loader_path", str(ext)],
        ["install_name_tool", "-add_rpath", "@loader_path/../pkg.libs", str(ext)],
        ["codesign", "-s", "-", "-f", str(ext)],
    ]


def test_patch_macos_extension_skips_existing_rpath(tmp_path: Path) -> None:
    """When the rpath already exists, the error is ignored."""
    ext = tmp_path / "_core.so"
    ext.write_bytes(b"")
    rpaths = ["@loader_path", "@loader_path/../mogemma.libs"]

    def mock_run_side_effect(args, **kwargs):
        if "-add_rpath" in args:
            raise subprocess.CalledProcessError(1, args, stderr="already contains LC_RPATH")
        return SimpleNamespace(stdout="")

    with (
        patch("hatch_mojo.runtime.subprocess.run", side_effect=mock_run_side_effect) as mock_run,
        patch("hatch_mojo.runtime._get_linked_libraries", return_value=[]),
    ):
        _patch_macos_extension(ext, ["libFoo.dylib"], rpaths)

    assert mock_run.call_count == 4
    assert mock_run.call_args_list[0].args[0] == ["otool", "-l", str(ext)]
    assert mock_run.call_args_list[3].args[0] == [
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

    def mock_resolve(target: Path, modular_lib: Path) -> set[str]:
        return {"libKGENCompilerRTShared.so", "libAsyncRTRuntimeGlobals.so", "libMSupportGlobals.so"}

    with (
        patch.object(sys, "platform", "linux"),
        patch("hatch_mojo.runtime.subprocess.run"),
        patch("hatch_mojo.runtime._resolve_modular_dependencies", side_effect=mock_resolve),
    ):
        bundle_runtime_libs(tmp_path, "build/mojo", [job], None)

    libs_dir = tmp_path / "build" / "mojo" / "mogemma.libs"
    for f in libs_dir.iterdir():
        assert f.stat().st_mode & stat.S_IWUSR, f"{f.name} should be writable"


# ── _write_license_notice ───────────────────────────────────────────────────


def test_license_notice_content(tmp_path: Path) -> None:
    """Notice file cites Apache-2.0 WITH LLVM-exception and lists libraries sorted."""
    libs_dir = tmp_path / "pkg.libs"
    libs_dir.mkdir()
    modular_lib = tmp_path / "modular" / "lib"
    modular_lib.mkdir(parents=True)

    filenames = ["libB.so", "libA.so"]
    entries = _write_license_notice(libs_dir, filenames, modular_lib)

    notice = libs_dir / "NOTICE.mojo-runtime"
    assert notice.exists()
    content = notice.read_text(encoding="utf-8")
    assert "  - libA.so" in content
    assert "  - libB.so" in content
    assert content.index("libA.so") < content.index("libB.so")
    assert "Apache License 2.0 with LLVM Exceptions" in content
    assert "Apache-2.0 WITH LLVM-exception" in content
    assert "https://github.com/modular/modular/blob/main/LICENSE" in content
    assert "Modular Inc, a Qualcomm Company" in content
    assert "Modular Community License" not in content
    assert "max-mojo-license" not in content
    assert "https://www.modular.com/legal/max-license" not in content
    assert entries[0] == (str(notice), "pkg.libs/NOTICE.mojo-runtime")


@pytest.mark.parametrize("max_lib", ["libMAXEngine.so", "libMOGGKernelAPI.so"])
def test_license_notice_appends_max_addendum_when_max_libs_present(
    tmp_path: Path,
    max_lib: str,
) -> None:
    libs_dir = tmp_path / "pkg.libs"
    libs_dir.mkdir()
    modular_lib = tmp_path / "modular" / "lib"
    modular_lib.mkdir(parents=True)

    _write_license_notice(libs_dir, ["libKGENCompilerRTShared.so", max_lib], modular_lib)
    content = (libs_dir / "NOTICE.mojo-runtime").read_text(encoding="utf-8")
    assert "Apache-2.0 WITH LLVM-exception" in content
    assert "MAX License" in content
    assert "https://www.modular.com/legal/max-license" in content
    assert "Section 1.5" in content


def test_bundle_copies_sdk_license_when_present(tmp_path: Path) -> None:
    """SDK LICENSE is copied as writable LICENSE.mojo-runtime when it exists."""
    libs_dir = tmp_path / "pkg.libs"
    libs_dir.mkdir()
    modular_dir = tmp_path / "modular"
    modular_lib = modular_dir / "lib"
    modular_lib.mkdir(parents=True)
    sdk_license = modular_dir / "LICENSE"
    sdk_license.write_text("Apache-2.0 WITH LLVM-exception text", encoding="utf-8")
    sdk_license.chmod(stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH)

    entries = _write_license_notice(libs_dir, ["libFoo.so"], modular_lib)

    assert len(entries) == 2
    license_dest = libs_dir / "LICENSE.mojo-runtime"
    assert license_dest.exists()
    assert license_dest.read_text(encoding="utf-8") == "Apache-2.0 WITH LLVM-exception text"
    assert license_dest.stat().st_mode & stat.S_IWUSR
    assert entries[1] == (str(license_dest), "pkg.libs/LICENSE.mojo-runtime")


@pytest.mark.parametrize(
    "dist_info_rel",
    [
        "mojo_compiler-1.2.0.dist-info/licenses/LICENSE",
        "mojo_compiler_mojo_libs-1.2.0.dist-info/licenses/LICENSE.txt",
        "mojo-1.2.0.dist-info/LICENSE",
    ],
)
def test_bundle_copies_sdk_license_from_dist_info(
    tmp_path: Path,
    dist_info_rel: str,
) -> None:
    libs_dir = tmp_path / "pkg.libs"
    libs_dir.mkdir()
    site_packages = tmp_path / "site-packages"
    modular_lib = site_packages / "modular" / "lib"
    modular_lib.mkdir(parents=True)

    dist_license = site_packages / dist_info_rel
    dist_license.parent.mkdir(parents=True, exist_ok=True)
    dist_license.write_text("Dist-info Apache-2.0 license", encoding="utf-8")
    dist_license.chmod(stat.S_IRUSR)

    entries = _write_license_notice(libs_dir, ["libKGENCompilerRTShared.so"], modular_lib)

    assert len(entries) == 2
    dest = libs_dir / "LICENSE.mojo-runtime"
    assert dest.read_text(encoding="utf-8") == "Dist-info Apache-2.0 license"
    assert dest.stat().st_mode & stat.S_IWUSR
    assert entries[1] == (str(dest), "pkg.libs/LICENSE.mojo-runtime")


def test_bundle_skips_sdk_license_when_absent(tmp_path: Path) -> None:
    """No LICENSE.mojo-runtime when SDK directory has no LICENSE file."""
    libs_dir = tmp_path / "pkg.libs"
    libs_dir.mkdir()
    modular_lib = tmp_path / "modular" / "lib"
    modular_lib.mkdir(parents=True)

    entries = _write_license_notice(libs_dir, ["libFoo.so"], modular_lib)

    assert len(entries) == 1
    assert not (libs_dir / "LICENSE.mojo-runtime").exists()


def test_bundle_includes_license_notice(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """bundle_runtime_libs() includes NOTICE.mojo-runtime in force_include."""
    modular = tmp_path / "modular"
    _make_modular_lib(modular)
    monkeypatch.setenv("MODULAR_LIB_DIR", str(modular / "lib"))

    job = _ext_job(tmp_path, module="mogemma._core")

    def mock_resolve(target: Path, modular_lib: Path) -> set[str]:
        return {"libKGENCompilerRTShared.so", "libAsyncRTRuntimeGlobals.so", "libMSupportGlobals.so"}

    with (
        patch.object(sys, "platform", "linux"),
        patch("hatch_mojo.runtime.subprocess.run"),
        patch("hatch_mojo.runtime._resolve_modular_dependencies", side_effect=mock_resolve),
    ):
        result = bundle_runtime_libs(tmp_path, "build/mojo", [job], None)

    assert any(v == "mogemma.libs/NOTICE.mojo-runtime" for v in result.force_include.values())
    notice_path = tmp_path / "build" / "mojo" / "mogemma.libs" / "NOTICE.mojo-runtime"
    assert notice_path.exists()
    content = notice_path.read_text()
    for base in ["KGENCompilerRTShared", "AsyncRTRuntimeGlobals", "MSupportGlobals"]:
        assert _lib_filename(base) in content


def test_bundle_full_flow_darwin(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """End-to-end macOS bundling with mocked subprocess."""

    def mock_resolve_darwin(target: Path, modular_lib: Path) -> set[str]:
        return {"libKGENCompilerRTShared.dylib", "libAsyncRTRuntimeGlobals.dylib", "libMSupportGlobals.dylib"}

    mock_result = SimpleNamespace(stdout="/path/to/lib:\n")
    with (
        patch.object(sys, "platform", "darwin"),
        patch("hatch_mojo.runtime.subprocess.run", return_value=mock_result),
        patch("hatch_mojo.runtime._resolve_modular_dependencies", side_effect=mock_resolve_darwin),
    ):
        modular = tmp_path / "modular"
        _make_modular_lib(modular)
        lib_dir = modular / "lib"
        monkeypatch.setenv("MODULAR_LIB_DIR", str(lib_dir))

        job = _ext_job(tmp_path, module="mogemma._core")
        result = bundle_runtime_libs(tmp_path, "build/mojo", [job], None)

    assert len(result.force_include) == 4
    libs_dir = tmp_path / "build" / "mojo" / "mogemma.libs"
    assert libs_dir.is_dir()

    for base in ["KGENCompilerRTShared", "AsyncRTRuntimeGlobals", "MSupportGlobals"]:
        filename = f"lib{base}.dylib"
        assert (libs_dir / filename).exists()
        assert any(v == f"mogemma.libs/{filename}" for v in result.force_include.values())


def test_bundle_scripts_and_data_executables_linux(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    modular = tmp_path / "modular"
    _make_modular_lib(modular)
    monkeypatch.setenv("MODULAR_LIB_DIR", str(modular / "lib"))

    cli_bin = tmp_path / "build/mojo/my-cli"
    cli_sub = tmp_path / "build/mojo/sub-cli"
    data_bin = tmp_path / "build/mojo/tool"
    cli_bin.parent.mkdir(parents=True, exist_ok=True)
    for target in (cli_bin, cli_sub, data_bin):
        target.write_bytes(b"elf")

    jobs = [
        BuildJob("cli1", tmp_path / "a.mojo", cli_bin, "executable", None, "scripts", "my-cli", (), (), (), {}, ()),
        BuildJob("cli2", tmp_path / "b.mojo", cli_sub, "executable", None, "scripts", "sub/my-cli", (), (), (), {}, ()),
        BuildJob("dat", tmp_path / "c.mojo", data_bin, "executable", None, "data", "share/sub/", (), (), (), {}, ()),
    ]

    with (
        patch.object(sys, "platform", "linux"),
        patch("hatch_mojo.runtime.subprocess.run") as mock_run,
        patch(
            "hatch_mojo.runtime._resolve_modular_dependencies",
            return_value={"libKGENCompilerRTShared.so"},
        ),
    ):
        result = bundle_runtime_libs(tmp_path, "build/mojo", jobs, None, dist_name="My-Pkg")

    assert result.force_include == {}
    assert "lib/my_pkg.libs/libKGENCompilerRTShared.so" in result.shared_data.values()
    assert "lib/my_pkg.libs/NOTICE.mojo-runtime" in result.shared_data.values()
    staged_dir = tmp_path / "build" / "mojo" / "shared" / "my_pkg.libs"
    assert (staged_dir / "libKGENCompilerRTShared.so") in result.staged_files
    assert (staged_dir / "NOTICE.mojo-runtime") in result.staged_files

    patchelf_calls = {c.args[0][3]: c.args[0][2] for c in mock_run.call_args_list if c.args[0][0] == "patchelf"}
    assert patchelf_calls[str(cli_bin)] == "$ORIGIN:$ORIGIN/../lib/my_pkg.libs"
    assert patchelf_calls[str(cli_sub)] == "$ORIGIN:$ORIGIN/../../lib/my_pkg.libs"
    assert patchelf_calls[str(data_bin)] == "$ORIGIN:$ORIGIN/../../lib/my_pkg.libs"


def test_bundle_shared_lib_package_and_root_fallback(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    modular = tmp_path / "modular"
    _make_modular_lib(modular)
    monkeypatch.setenv("MODULAR_LIB_DIR", str(modular / "lib"))

    pkg_lib = tmp_path / "build/mojo/libpkg.so"
    root_lib = tmp_path / "build/mojo/libfoo.so"
    pkg_lib.parent.mkdir(parents=True, exist_ok=True)
    pkg_lib.write_bytes(b"elf")
    root_lib.write_bytes(b"elf")

    jobs = [
        BuildJob(
            "pkglib",
            tmp_path / "a.mojo",
            pkg_lib,
            "shared-lib",
            None,
            "package",
            "my_pkg/native",
            (),
            (),
            (),
            {},
            (),
        ),
        BuildJob("rootlib", tmp_path / "b.mojo", root_lib, "shared-lib", None, "root", "libfoo.so", (), (), (), {}, ()),
    ]

    with (
        patch.object(sys, "platform", "linux"),
        patch("hatch_mojo.runtime.subprocess.run") as mock_run,
        patch(
            "hatch_mojo.runtime._resolve_modular_dependencies",
            return_value={"libKGENCompilerRTShared.so"},
        ),
    ):
        result = bundle_runtime_libs(tmp_path, "build/mojo", jobs, None, dist_name=None)

    assert "my_pkg.libs/libKGENCompilerRTShared.so" in result.force_include.values()
    assert "mojo_runtime.libs/libKGENCompilerRTShared.so" in result.force_include.values()
    assert result.shared_data == {}

    patchelf_calls = {c.args[0][3]: c.args[0][2] for c in mock_run.call_args_list if c.args[0][0] == "patchelf"}
    assert patchelf_calls[str(pkg_lib)] == "$ORIGIN:$ORIGIN/../../my_pkg.libs"
    assert patchelf_calls[str(root_lib)] == "$ORIGIN:$ORIGIN/mojo_runtime.libs"


def test_bundle_darwin_shared_lib_and_scripts_executable(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    with patch.object(sys, "platform", "darwin"):
        modular = tmp_path / "modular"
        _make_modular_lib(modular)
        monkeypatch.setenv("MODULAR_LIB_DIR", str(modular / "lib"))

        shlib = tmp_path / "build/mojo/libfoo.dylib"
        cli = tmp_path / "build/mojo/my-cli"
        shlib.parent.mkdir(parents=True, exist_ok=True)
        shlib.write_bytes(b"macho")
        cli.write_bytes(b"macho")

        jobs = [
            BuildJob(
                "shlib",
                tmp_path / "a.mojo",
                shlib,
                "shared-lib",
                None,
                "package",
                "my_pkg/native",
                (),
                (),
                (),
                {},
                (),
            ),
            BuildJob("cli", tmp_path / "b.mojo", cli, "executable", None, "scripts", "my-cli", (), (), (), {}, ()),
        ]

        mock_result = SimpleNamespace(stdout="/path:\n")
        with (
            patch("hatch_mojo.runtime.subprocess.run", return_value=mock_result) as mock_run,
            patch(
                "hatch_mojo.runtime._resolve_modular_dependencies",
                return_value={"libKGENCompilerRTShared.dylib"},
            ),
        ):
            result = bundle_runtime_libs(tmp_path, "build/mojo", jobs, None, dist_name="My-Pkg")

    assert "my_pkg.libs/libKGENCompilerRTShared.dylib" in result.force_include.values()
    assert "lib/my_pkg.libs/libKGENCompilerRTShared.dylib" in result.shared_data.values()

    arg_lists = [c.args[0] for c in mock_run.call_args_list]
    assert ["install_name_tool", "-id", "@rpath/libfoo.dylib", str(shlib)] in arg_lists
    assert ["install_name_tool", "-add_rpath", "@loader_path/../../my_pkg.libs", str(shlib)] in arg_lists
    assert ["install_name_tool", "-add_rpath", "@loader_path/../lib/my_pkg.libs", str(cli)] in arg_lists
    assert ["codesign", "-s", "-", "-f", str(shlib)] in arg_lists
    assert ["codesign", "-s", "-", "-f", str(cli)] in arg_lists


def test_patch_editable_runtime_persistent_sdk_linux(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = tmp_path / "project"
    root.mkdir()
    sdk_dir = _make_modular_lib(root / ".venv" / "modular")
    monkeypatch.setenv("MODULAR_LIB_DIR", str(sdk_dir))

    ext = root / "src" / "pkg" / "_core.so"
    ext.parent.mkdir(parents=True)
    ext.write_bytes(b"elf")
    job = BuildJob("core", root / "core.mojo", ext, "python-extension", "pkg._core", None, None, (), (), (), {}, ())

    with (
        patch.object(sys, "platform", "linux"),
        patch("hatch_mojo.runtime.subprocess.run") as mock_run,
    ):
        staged = patch_editable_runtime(root, "build/mojo", [job], None)

    assert staged == ()
    assert not (root / "build" / "mojo" / "editable.libs").exists()
    mock_run.assert_called_once_with(
        ["patchelf", "--set-rpath", str(sdk_dir.resolve()), str(ext)],
        check=True,
        capture_output=True,
    )


def test_patch_editable_runtime_persistent_sdk_darwin(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = tmp_path / "project"
    root.mkdir()
    with patch.object(sys, "platform", "darwin"):
        sdk_dir = _make_modular_lib(root / ".venv" / "modular")
        monkeypatch.setenv("MODULAR_LIB_DIR", str(sdk_dir))

        ext = root / "src" / "pkg" / "_core.so"
        ext.parent.mkdir(parents=True)
        ext.write_bytes(b"macho")
        job = BuildJob("core", root / "core.mojo", ext, "python-extension", "pkg._core", None, None, (), (), (), {}, ())

        linked = [str(sdk_dir / "libKGENCompilerRTShared.dylib")]
        with (
            patch("hatch_mojo.runtime.subprocess.run", return_value=SimpleNamespace(stdout="")) as mock_run,
            patch("hatch_mojo.runtime._get_linked_libraries", return_value=linked),
        ):
            staged = patch_editable_runtime(root, "build/mojo", [job], None)

    assert staged == ()
    assert not (root / "build" / "mojo" / "editable.libs").exists()
    arg_lists = [c.args[0] for c in mock_run.call_args_list]
    assert ["otool", "-l", str(ext)] in arg_lists
    assert [
        "install_name_tool",
        "-change",
        str(sdk_dir / "libKGENCompilerRTShared.dylib"),
        "@rpath/libKGENCompilerRTShared.dylib",
        str(ext),
    ] in arg_lists
    assert ["install_name_tool", "-add_rpath", str(sdk_dir.resolve()), str(ext)] in arg_lists
    assert arg_lists[-1] == ["codesign", "-s", "-", "-f", str(ext)]


def test_patch_editable_runtime_ephemeral_sdk_linux_and_darwin(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "project"
    root.mkdir()
    ext = root / "src" / "pkg" / "_core.so"
    ext.parent.mkdir(parents=True)
    ext.write_bytes(b"elf")
    job = BuildJob("core", root / "core.mojo", ext, "python-extension", "pkg._core", None, None, (), (), (), {}, ())

    ephemeral_tmp = _make_modular_lib(tmp_path / "pep517_isolated" / "modular")
    for lib_file in ephemeral_tmp.iterdir():
        lib_file.chmod(stat.S_IRUSR)
    monkeypatch.setenv("MODULAR_LIB_DIR", str(ephemeral_tmp))

    with (
        patch.object(sys, "platform", "linux"),
        patch("hatch_mojo.runtime.subprocess.run") as mock_run,
        patch(
            "hatch_mojo.runtime._resolve_modular_dependencies",
            return_value={"libKGENCompilerRTShared.so"},
        ),
    ):
        staged = patch_editable_runtime(root, "build/mojo", [job], None)

    editable_libs = root / "build" / "mojo" / "editable.libs"
    assert editable_libs.is_dir()
    staged_lib = editable_libs / "libKGENCompilerRTShared.so"
    assert staged_lib in staged
    assert (editable_libs / "NOTICE.mojo-runtime") in staged
    assert staged_lib.stat().st_mode & stat.S_IWUSR
    patchelf_calls = {c.args[0][3]: c.args[0][2] for c in mock_run.call_args_list if c.args[0][0] == "patchelf"}
    assert patchelf_calls[str(staged_lib)] == "$ORIGIN"
    assert patchelf_calls[str(ext)] == str(editable_libs.resolve())

    with patch.object(sys, "platform", "darwin"):
        uv_cache_sdk = _make_modular_lib(
            root.parent / "fake_home" / ".cache" / "uv" / "builds-v0" / ".tmpAbCdEf" / "modular"
        )
        monkeypatch.setenv("MODULAR_LIB_DIR", str(uv_cache_sdk))
        with (
            patch("hatch_mojo.runtime.tempfile.gettempdir", return_value="/nonexistent_system_tmp"),
            patch("hatch_mojo.runtime.subprocess.run", return_value=SimpleNamespace(stdout="")) as mock_mac_run,
            patch(
                "hatch_mojo.runtime._resolve_modular_dependencies",
                return_value={"libKGENCompilerRTShared.dylib"},
            ),
        ):
            staged_mac = patch_editable_runtime(root, "build/mojo_mac", [job], None)

    mac_libs = root / "build" / "mojo_mac" / "editable.libs"
    assert (mac_libs / "libKGENCompilerRTShared.dylib") in staged_mac
    mac_args = [c.args[0] for c in mock_mac_run.call_args_list]
    assert ["install_name_tool", "-add_rpath", str(mac_libs.resolve()), str(ext)] in mac_args
    assert ["codesign", "-s", "-", "-f", str(ext)] in mac_args


# ── test helpers ───────────────────────────────────────────────────────────


def calls_contain_flag(call_list: Any, flag: str) -> bool:
    """Check if any call in a mock's call_args_list contains the given flag."""
    return any(flag in call.args[0] for call in call_list)
