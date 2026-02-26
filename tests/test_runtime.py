from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from hatch_mojo.runtime import (
    _RUNTIME_LIB_BASES,
    _compute_extension_rpath,
    _lib_filename,
    _patch_rpath,
    _sentinel,
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
