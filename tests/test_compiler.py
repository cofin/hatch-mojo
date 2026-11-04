from __future__ import annotations

import importlib
import json
import subprocess
import sys
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from hatch_mojo.compiler import (
    CACHE_FILENAME,
    RAW_CACHE_DIRNAME,
    build_command,
    compile_job,
    compute_job_digest,
    discover_mojo,
)
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


def test_compute_job_digest_tracks_sources_includes_flags_deps_and_skips_cache_dir(tmp_path: Path) -> None:
    compiler_bin = tmp_path / "bin" / "mojo"
    compiler_bin.parent.mkdir(parents=True)
    compiler_bin.write_bytes(b"mojo-v1")

    src_dir = tmp_path / "src"
    src_dir.mkdir()
    entry = src_dir / "main.mojo"
    sibling = src_dir / "helper.mojo"
    entry.write_text("def main(): pass\n", encoding="utf-8")
    sibling.write_text("def helper(): pass\n", encoding="utf-8")

    cache_dir = src_dir / "build_cache"
    raw_dir = cache_dir / RAW_CACHE_DIRNAME
    raw_dir.mkdir(parents=True)
    (cache_dir / "cached_ignored.mojoc").write_bytes(b"ignored-ir")

    inc_dir = tmp_path / "include"
    nested_inc = inc_dir / "sub"
    nested_inc.mkdir(parents=True)
    header_mojoc = nested_inc / "api.mojoc"
    header_mojoc.write_bytes(b"ir-v1")

    linked_obj = tmp_path / "build" / "kernel.o"
    linked_obj.parent.mkdir(parents=True)
    linked_obj.write_bytes(b"obj-v1")

    (cache_dir / CACHE_FILENAME).write_text(json.dumps({"upstream": "digest-up-1"}), encoding="utf-8")

    base_job = BuildJob(
        name="app",
        input_path=entry,
        output_path=tmp_path / "build" / "app.so",
        emit="python-extension",
        module="pkg._app",
        install_kind=None,
        install_path=None,
        include_dirs=("include",),
        defines=("OPT=1",),
        flags=("build/kernel.o",),
        env={"MOJO_FLAG": "a"},
        depends_on=("upstream",),
    )

    d0 = compute_job_digest(mojo_bin=str(compiler_bin), root=tmp_path, job=base_job, cache_dir=cache_dir)
    assert d0 == compute_job_digest(mojo_bin=str(compiler_bin), root=tmp_path, job=base_job, cache_dir=cache_dir)

    (cache_dir / "cached_ignored.mojoc").write_bytes(b"changed-ignored-ir")
    assert d0 == compute_job_digest(mojo_bin=str(compiler_bin), root=tmp_path, job=base_job, cache_dir=cache_dir)

    sibling.write_text("def helper(): return 1\n", encoding="utf-8")
    d_sibling = compute_job_digest(mojo_bin=str(compiler_bin), root=tmp_path, job=base_job, cache_dir=cache_dir)
    assert d_sibling != d0

    header_mojoc.write_bytes(b"ir-v2")
    d_inc = compute_job_digest(mojo_bin=str(compiler_bin), root=tmp_path, job=base_job, cache_dir=cache_dir)
    assert d_inc != d_sibling

    linked_obj.write_bytes(b"obj-v2")
    d_obj = compute_job_digest(mojo_bin=str(compiler_bin), root=tmp_path, job=base_job, cache_dir=cache_dir)
    assert d_obj != d_inc

    (cache_dir / CACHE_FILENAME).write_text(json.dumps({"upstream": "digest-up-2"}), encoding="utf-8")
    d_dep = compute_job_digest(mojo_bin=str(compiler_bin), root=tmp_path, job=base_job, cache_dir=cache_dir)
    assert d_dep != d_obj

    env_job = replace(base_job, env={"MOJO_FLAG": "b"})
    d_env = compute_job_digest(mojo_bin=str(compiler_bin), root=tmp_path, job=env_job, cache_dir=cache_dir)
    assert d_env != d_dep

    compiler_bin.write_bytes(b"mojo-v2-longer-binary")
    d_comp = compute_job_digest(mojo_bin=str(compiler_bin), root=tmp_path, job=env_job, cache_dir=cache_dir)
    assert d_comp != d_env


def test_compile_job_cache_disabled_always_compiles(tmp_path: Path) -> None:
    counter = tmp_path / "count.txt"
    counter.write_text("0", encoding="utf-8")
    fake_mojo = tmp_path / "fake_mojo"
    fake_mojo.write_text(
        "#!/usr/bin/env python3\n"
        "import pathlib, sys\n"
        f"c = pathlib.Path({str(counter)!r})\n"
        "n = int(c.read_text()) + 1\n"
        "c.write_text(str(n))\n"
        "out = pathlib.Path(sys.argv[sys.argv.index('-o') + 1])\n"
        "out.parent.mkdir(parents=True, exist_ok=True)\n"
        "out.write_bytes(f'bin-{n}'.encode())\n",
        encoding="utf-8",
    )
    fake_mojo.chmod(0o755)

    src = tmp_path / "src" / "core.mojo"
    src.parent.mkdir(parents=True)
    src.write_text("def f(): pass\n", encoding="utf-8")
    job = BuildJob(
        name="core",
        input_path=src,
        output_path=tmp_path / "out" / "_core.so",
        emit="python-extension",
        module="pkg._core",
        install_kind=None,
        install_path=None,
        include_dirs=(),
        defines=(),
        flags=(),
        env={},
        depends_on=(),
    )
    cache_dir = tmp_path / "build" / "mojo"

    ok1, _ = compile_job(mojo_bin=str(fake_mojo), root=tmp_path, job=job, use_cache=False, cache_dir=cache_dir)
    ok2, _ = compile_job(mojo_bin=str(fake_mojo), root=tmp_path, job=job, use_cache=False, cache_dir=cache_dir)
    assert ok1 is True
    assert ok2 is True
    assert int(counter.read_text(encoding="utf-8")) == 2
    assert not (cache_dir / CACHE_FILENAME).exists()


def test_discover_mojo_package_import_error_and_missing_binary(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("HATCH_MOJO_BIN", raising=False)
    monkeypatch.setitem(sys.modules, "mojo", None)
    monkeypatch.setitem(sys.modules, "mojo._package_root", None)
    monkeypatch.setattr("hatch_mojo.compiler.shutil.which", lambda _: "/usr/bin/fallback-mojo")
    assert discover_mojo(tmp_path, None) == "/usr/bin/fallback-mojo"

    empty_sdk = tmp_path / "empty_sdk"
    empty_sdk.mkdir()
    real_import = importlib.import_module

    def fake_import_empty(name: str, package: str | None = None) -> object:
        if name == "mojo._package_root":
            return SimpleNamespace(get_package_root=lambda: str(empty_sdk))
        return real_import(name, package)

    monkeypatch.setattr(importlib, "import_module", fake_import_empty)
    assert discover_mojo(tmp_path, None) == "/usr/bin/fallback-mojo"


def test_compile_job_win32_suffix_probing_and_non_shebang_commands(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("hatch_mojo.compiler.sys.platform", "win32")
    monkeypatch.setattr("hatch_mojo.compiler.shutil.which", lambda _: None)
    tools_dir = tmp_path / "tools"
    tools_dir.mkdir()
    cmd_shim = tools_dir / "mojo.cmd"
    cmd_shim.write_text("@echo off\r\n", encoding="utf-8")
    plain_file = tmp_path / "plain_bin"
    plain_file.write_bytes(b"MZ-no-shebang")

    captured: list[list[str]] = []

    def fake_run(cmd: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        captured.append(list(cmd))
        return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="", stderr="")

    monkeypatch.setattr("hatch_mojo.compiler.subprocess.run", fake_run)
    job = _job(tmp_path)

    ok_probed, _ = compile_job(mojo_bin="tools/mojo", root=tmp_path, job=job)
    assert ok_probed is True
    assert captured[-1][0] == "tools/mojo.cmd"

    ok_plain, _ = compile_job(mojo_bin="plain_bin", root=tmp_path, job=job)
    assert ok_plain is True
    assert captured[-1][0] == "plain_bin"

    ok_missing, _ = compile_job(mojo_bin="tools/missing_mojo", root=tmp_path, job=job)
    assert ok_missing is True
    assert captured[-1][0] == "tools/missing_mojo"

    ok_missing_exe, _ = compile_job(mojo_bin="tools/missing.exe", root=tmp_path, job=job)
    assert ok_missing_exe is True
    assert captured[-1][0] == "tools/missing.exe"


def test_compute_job_digest_and_cache_edge_cases(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("hatch_mojo.compiler.shutil.which", lambda _: None)
    root = tmp_path / "project"
    root.mkdir()
    ext_src = tmp_path / "external_dir" / "ext.mojo"
    ext_src.parent.mkdir()
    ext_src.write_text("def ext(): pass\n", encoding="utf-8")
    (ext_src.parent / "dir_named.mojo").mkdir()

    cache_dir = root / "build" / "mojo"
    raw_dir = cache_dir / RAW_CACHE_DIRNAME
    raw_dir.mkdir(parents=True)
    (raw_dir / "ignored_raw.mojoc").write_bytes(b"raw-bytes")
    (cache_dir / "explicit_ir.mojoc").write_bytes(b"explicit-ir")

    job_missing_in = BuildJob(
        name="missing_in",
        input_path=root / "nonexistent_dir" / "missing.mojo",
        output_path=root / "build" / "out.so",
        emit="python-extension",
        module="pkg._out",
        install_kind=None,
        install_path=None,
        include_dirs=("missing_inc", str(cache_dir)),
        defines=(),
        flags=("-O3",),
        env={},
        depends_on=(),
    )
    d_none_cache = compute_job_digest(mojo_bin="unstatable-mojo", root=root, job=job_missing_in, cache_dir=None)
    assert len(d_none_cache) == 64

    (cache_dir / CACHE_FILENAME).write_text("{corrupt-json", encoding="utf-8")
    d_corrupt = compute_job_digest(mojo_bin="unstatable-mojo", root=root, job=job_missing_in, cache_dir=cache_dir)
    (cache_dir / CACHE_FILENAME).write_text("[1, 2, 3]", encoding="utf-8")
    d_list = compute_job_digest(mojo_bin="unstatable-mojo", root=root, job=job_missing_in, cache_dir=cache_dir)
    assert d_corrupt == d_list

    ext_job = replace(job_missing_in, name="ext_job", input_path=ext_src)
    d_ext_1 = compute_job_digest(mojo_bin="unstatable-mojo", root=root, job=ext_job, cache_dir=cache_dir)
    (raw_dir / "ignored_raw.mojoc").write_bytes(b"raw-bytes-mutated")
    assert d_ext_1 == compute_job_digest(mojo_bin="unstatable-mojo", root=root, job=ext_job, cache_dir=cache_dir)

    monkeypatch.setattr(
        "hatch_mojo.compiler.subprocess.run",
        lambda cmd, **_kw: subprocess.CompletedProcess(args=cmd, returncode=0, stdout="", stderr=""),
    )
    ok, _ = compile_job(mojo_bin="unstatable-mojo", root=root, job=ext_job, use_cache=True, cache_dir=cache_dir)
    assert ok is True
    saved_cache = json.loads((cache_dir / CACHE_FILENAME).read_text(encoding="utf-8"))
    assert saved_cache["ext_job"] == d_ext_1
