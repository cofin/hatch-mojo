from __future__ import annotations

import importlib
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from hatch_mojo.compiler import build_command, compile_job, discover_mojo
from hatch_mojo.types import BuildJob


def _job(tmp_path: Path) -> BuildJob:
    return BuildJob(
        name="core",
        input_path=tmp_path / "src/mo/pkg/core.mojo",
        output_path=tmp_path / "src/py/pkg/_core.so",
        emit="python-extension",
        module="pkg._core",
        install_kind=None,
        install_path=None,
        include_dirs=("src/mo",),
        defines=("DEBUG=0",),
        flags=("--opt-level", "3"),
        env={},
        depends_on=(),
    )


def test_build_command(tmp_path: Path) -> None:
    job = _job(tmp_path)
    command = build_command("mojo", tmp_path, job)
    assert command[:4] == ["mojo", "build", "--emit", "shared-lib"]
    assert "-I" in command
    assert "-D" in command


def test_build_command_executable_uses_emit_exe(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("hatch_mojo.compiler.sys.platform", "darwin")
    job = BuildJob(
        name="cli",
        input_path=tmp_path / "src/cli.mojo",
        output_path=tmp_path / "build/mojo/cli",
        emit="executable",
        module=None,
        install_kind="scripts",
        install_path="bin",
        include_dirs=("src",),
        defines=("FAST=1",),
        flags=("-O3",),
        env={},
        depends_on=(),
    )
    command = build_command("mojo", tmp_path, job)
    assert command[:4] == ["mojo", "build", "--emit", "exe"]
    assert "-headerpad_max_install_names" in command
    assert command[-3:] == ["src/cli.mojo", "-o", "build/mojo/cli"]


def test_build_command_mojoc_uses_precompile(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("hatch_mojo.compiler.sys.platform", "darwin")
    job = BuildJob(
        name="pkg_ir",
        input_path=tmp_path / "src/pkg/mod.mojo",
        output_path=tmp_path / "build/mojo/mod.mojoc",
        emit="mojoc",
        module=None,
        install_kind="package",
        install_path="pkg",
        include_dirs=("src",),
        defines=("DEBUG=0",),
        flags=("--debug-level", "none"),
        env={},
        depends_on=(),
    )
    command = build_command("mojo", tmp_path, job)
    assert command == [
        "mojo",
        "precompile",
        "-I",
        "src",
        "-D",
        "DEBUG=0",
        "--debug-level",
        "none",
        "src/pkg/mod.mojo",
        "-o",
        "build/mojo/mod.mojoc",
    ]
    assert "--emit" not in command
    assert "-headerpad_max_install_names" not in command


def test_build_command_outside_root_paths(tmp_path: Path) -> None:
    root = tmp_path / "project"
    root.mkdir()
    ext_in = tmp_path / "external_src.mojo"
    ext_out = tmp_path / "external_out.so"
    job = BuildJob(
        name="ext",
        input_path=ext_in,
        output_path=ext_out,
        emit="python-extension",
        module="pkg._ext",
        install_kind=None,
        install_path=None,
        include_dirs=(),
        defines=(),
        flags=(),
        env={},
        depends_on=(),
    )
    command = build_command("mojo", root, job)
    assert command[-3:] == [str(ext_in), "-o", str(ext_out)]


def test_discover_mojo_missing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("HATCH_MOJO_BIN", raising=False)
    monkeypatch.setattr("hatch_mojo.compiler._discover_mojo_from_package", lambda: None, raising=False)
    monkeypatch.setattr("hatch_mojo.compiler.shutil.which", lambda _: None)
    with pytest.raises(FileNotFoundError, match="mojo-compiler"):
        discover_mojo(tmp_path, None)


def test_discover_mojo_prefers_configured(tmp_path: Path) -> None:
    assert discover_mojo(tmp_path, "/custom/mojo") == "/custom/mojo"


def test_discover_mojo_from_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HATCH_MOJO_BIN", "/env/mojo")
    assert discover_mojo(tmp_path, None) == "/env/mojo"


def test_discover_mojo_from_package_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("HATCH_MOJO_BIN", raising=False)
    monkeypatch.setattr("hatch_mojo.compiler.sys.platform", "linux")
    sdk = tmp_path / "mojo_sdk"
    mojo_exe = sdk / "bin" / "mojo"
    mojo_exe.parent.mkdir(parents=True)
    mojo_exe.write_text("", encoding="utf-8")

    real_import = importlib.import_module

    def fake_import(name: str, package: str | None = None) -> object:
        if name == "mojo._package_root":
            return SimpleNamespace(get_package_root=lambda: str(sdk))
        return real_import(name, package)

    monkeypatch.setattr(importlib, "import_module", fake_import)
    monkeypatch.setattr("hatch_mojo.compiler.shutil.which", lambda _: "/usr/bin/ambient-mojo")
    assert discover_mojo(tmp_path, None) == str(mojo_exe)

    def fake_import_none(name: str, package: str | None = None) -> object:
        if name == "mojo._package_root":
            return SimpleNamespace(get_package_root=lambda: None)
        return real_import(name, package)

    monkeypatch.setattr(importlib, "import_module", fake_import_none)
    assert discover_mojo(tmp_path, None) == "/usr/bin/ambient-mojo"


def test_discover_mojo_from_venv(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("HATCH_MOJO_BIN", raising=False)
    monkeypatch.setattr("hatch_mojo.compiler.sys.platform", "linux")
    monkeypatch.setattr("hatch_mojo.compiler._discover_mojo_from_package", lambda: None, raising=False)
    monkeypatch.setattr("hatch_mojo.compiler.shutil.which", lambda _: None)
    candidate = tmp_path / ".venv" / "bin" / "mojo"
    candidate.parent.mkdir(parents=True)
    candidate.write_text("", encoding="utf-8")
    assert discover_mojo(tmp_path, None) == str(candidate)


def test_discover_mojo_from_windows_venv_scripts(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("HATCH_MOJO_BIN", raising=False)
    monkeypatch.setattr("hatch_mojo.compiler.sys.platform", "win32")
    monkeypatch.setattr("hatch_mojo.compiler._discover_mojo_from_package", lambda: None, raising=False)
    monkeypatch.setattr("hatch_mojo.compiler.shutil.which", lambda _: None)
    scripts_dir = tmp_path / ".venv" / "Scripts"
    scripts_dir.mkdir(parents=True)
    cmd_shim = scripts_dir / "mojo.cmd"
    cmd_shim.write_text("@echo off\n", encoding="utf-8")
    assert discover_mojo(tmp_path, None) == str(cmd_shim)

    exe_bin = scripts_dir / "mojo.exe"
    exe_bin.write_bytes(b"MZ")
    assert discover_mojo(tmp_path, None) == str(exe_bin)


def test_compile_job_non_fail_fast_returns_false(tmp_path: Path) -> None:
    source = tmp_path / "src/mo/pkg/core.mojo"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text("", encoding="utf-8")
    job = _job(tmp_path)
    success, log = compile_job(mojo_bin=sys.executable, root=tmp_path, job=job, fail_fast=False)
    assert success is False
    assert "exit=" in log


def test_compile_job_fail_fast_raises(tmp_path: Path) -> None:
    source = tmp_path / "src/mo/pkg/core.mojo"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text("", encoding="utf-8")
    job = _job(tmp_path)
    with pytest.raises(RuntimeError):
        compile_job(mojo_bin=sys.executable, root=tmp_path, job=job, fail_fast=True)


def test_compile_job_win32_cmd_shim_not_wrapped_with_python(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("hatch_mojo.compiler.sys.platform", "win32")
    shim = tmp_path / "mojo.cmd"
    shim.write_text("@echo off\r\n", encoding="utf-8")
    captured: list[list[str]] = []

    def fake_run(cmd: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        captured.append(list(cmd))
        return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="", stderr="")

    monkeypatch.setattr("hatch_mojo.compiler.subprocess.run", fake_run)
    monkeypatch.setattr(
        "hatch_mojo.compiler.shutil.which",
        lambda name: str(shim) if name == "mojo" else None,
    )
    job = _job(tmp_path)

    ok_shim, _ = compile_job(mojo_bin=str(shim), root=tmp_path, job=job)
    assert ok_shim is True
    assert captured[-1][0] == str(shim)

    ok_bare, _ = compile_job(mojo_bin="mojo", root=tmp_path, job=job)
    assert ok_bare is True
    assert captured[-1][0] == str(shim)


def test_compile_job_win32_shebang_script_wrapped_with_python(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("hatch_mojo.compiler.sys.platform", "win32")
    monkeypatch.setattr("hatch_mojo.compiler.shutil.which", lambda _: None)
    stub = tmp_path / "fake_mojo"
    stub.write_text("#!/usr/bin/env python3\nimport sys\n", encoding="utf-8")
    captured: list[list[str]] = []

    def fake_run(cmd: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        captured.append(list(cmd))
        return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="", stderr="")

    monkeypatch.setattr("hatch_mojo.compiler.subprocess.run", fake_run)
    job = _job(tmp_path)

    ok_abs, _ = compile_job(mojo_bin=str(stub), root=tmp_path, job=job)
    assert ok_abs is True
    assert captured[-1][:2] == [sys.executable, str(stub)]

    ok_rel, _ = compile_job(mojo_bin="fake_mojo", root=tmp_path, job=job)
    assert ok_rel is True
    assert captured[-1][:2] == [sys.executable, "fake_mojo"]
