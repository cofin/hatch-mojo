from __future__ import annotations

from pathlib import Path

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


def test_discover_mojo_missing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("HATCH_MOJO_BIN", raising=False)
    monkeypatch.setattr("hatch_mojo.compiler.shutil.which", lambda _: None)
    with pytest.raises(FileNotFoundError):
        discover_mojo(tmp_path, None)


def test_discover_mojo_prefers_configured(tmp_path: Path) -> None:
    assert discover_mojo(tmp_path, "/custom/mojo") == "/custom/mojo"


def test_discover_mojo_from_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HATCH_MOJO_BIN", "/env/mojo")
    assert discover_mojo(tmp_path, None) == "/env/mojo"


def test_discover_mojo_from_venv(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("HATCH_MOJO_BIN", raising=False)
    monkeypatch.setattr("hatch_mojo.compiler.shutil.which", lambda _: None)
    candidate = tmp_path / ".venv" / "bin" / "mojo"
    candidate.parent.mkdir(parents=True)
    candidate.write_text("", encoding="utf-8")
    assert discover_mojo(tmp_path, None) == str(candidate)


def test_compile_job_non_fail_fast_returns_false(tmp_path: Path) -> None:
    source = tmp_path / "src/mo/pkg/core.mojo"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text("", encoding="utf-8")
    job = _job(tmp_path)
    success, log = compile_job(mojo_bin="python3", root=tmp_path, job=job, fail_fast=False)
    assert success is False
    assert "exit=" in log


def test_compile_job_fail_fast_raises(tmp_path: Path) -> None:
    source = tmp_path / "src/mo/pkg/core.mojo"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text("", encoding="utf-8")
    job = _job(tmp_path)
    with pytest.raises(RuntimeError):
        compile_job(mojo_bin="python3", root=tmp_path, job=job, fail_fast=True)
