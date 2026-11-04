from __future__ import annotations

import shutil
from dataclasses import replace
from pathlib import Path

from hatch_mojo.compiler import RAW_CACHE_DIRNAME, compile_job, compute_job_digest
from hatch_mojo.types import BuildJob


def _write_fake_mojo(path: Path) -> None:
    path.write_text(
        "#!/usr/bin/env python3\n"
        "import pathlib\n"
        "import sys\n"
        "output = pathlib.Path(sys.argv[sys.argv.index('-o') + 1])\n"
        "output.parent.mkdir(parents=True, exist_ok=True)\n"
        "output.write_bytes(b'ok')\n",
        encoding="utf-8",
    )
    path.chmod(0o755)


def test_compile_job_creates_output(tmp_path: Path) -> None:
    fake_mojo = tmp_path / "mojo"
    _write_fake_mojo(fake_mojo)
    source = tmp_path / "src/mo/pkg/core.mojo"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text("def main():\n    pass\n", encoding="utf-8")
    output = tmp_path / "src/py/pkg/_core.so"

    job = BuildJob(
        name="core",
        input_path=source,
        output_path=output,
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
    success, _ = compile_job(mojo_bin=str(fake_mojo), root=tmp_path, job=job)
    assert success
    assert output.exists()


def test_compile_job_cache_hit_restores_pristine_raw_binary_and_invalidates_on_changes(tmp_path: Path) -> None:
    counter = tmp_path / "invocations.txt"
    counter.write_text("0", encoding="utf-8")
    fake_mojo = tmp_path / "mojo"
    fake_mojo.write_text(
        "#!/usr/bin/env python3\n"
        "import pathlib\n"
        "import sys\n"
        f"counter = pathlib.Path({str(counter)!r})\n"
        "count = int(counter.read_text(encoding='utf-8')) + 1\n"
        "counter.write_text(str(count), encoding='utf-8')\n"
        "output = pathlib.Path(sys.argv[sys.argv.index('-o') + 1])\n"
        "output.parent.mkdir(parents=True, exist_ok=True)\n"
        "output.write_bytes(f'pristine-{count}'.encode('utf-8'))\n",
        encoding="utf-8",
    )
    fake_mojo.chmod(0o755)

    source = tmp_path / "src" / "mo" / "core.mojo"
    source.parent.mkdir(parents=True)
    source.write_text("def main():\n    pass\n", encoding="utf-8")

    nested_header = tmp_path / "inc" / "nested" / "types.mojo"
    nested_header.parent.mkdir(parents=True)
    nested_header.write_text("alias X = 1\n", encoding="utf-8")

    linked_obj = tmp_path / "objs" / "helper.o"
    linked_obj.parent.mkdir(parents=True)
    linked_obj.write_bytes(b"obj-1")

    cache_dir = tmp_path / "build" / "mojo"
    output = cache_dir / "pkg" / "_core.so"
    job = BuildJob(
        name="core",
        input_path=source,
        output_path=output,
        emit="python-extension",
        module="pkg._core",
        install_kind=None,
        install_path=None,
        include_dirs=("inc",),
        defines=("FAST=1",),
        flags=("objs/helper.o",),
        env={},
        depends_on=(),
    )

    ok1, log1 = compile_job(mojo_bin=str(fake_mojo), root=tmp_path, job=job, use_cache=True, cache_dir=cache_dir)
    assert ok1 is True
    assert "cache=hit" not in log1
    assert int(counter.read_text(encoding="utf-8")) == 1
    assert output.read_bytes() == b"pristine-1"
    digest1 = compute_job_digest(mojo_bin=str(fake_mojo), root=tmp_path, job=job, cache_dir=cache_dir)
    raw_file = cache_dir / RAW_CACHE_DIRNAME / f"{digest1}{output.suffix}"
    assert raw_file.is_file()
    assert raw_file.read_bytes() == b"pristine-1"

    output.write_bytes(b"patched-rpath-binary")
    ok2, log2 = compile_job(mojo_bin=str(fake_mojo), root=tmp_path, job=job, use_cache=True, cache_dir=cache_dir)
    assert ok2 is True
    assert "cache=hit" in log2
    assert int(counter.read_text(encoding="utf-8")) == 1
    assert output.read_bytes() == b"pristine-1"

    output.unlink()
    ok2b, log2b = compile_job(mojo_bin=str(fake_mojo), root=tmp_path, job=job, use_cache=True, cache_dir=cache_dir)
    assert ok2b is True
    assert "cache=hit" in log2b
    assert int(counter.read_text(encoding="utf-8")) == 1
    assert output.read_bytes() == b"pristine-1"

    nested_header.write_text("alias X = 2\n", encoding="utf-8")
    ok3, log3 = compile_job(mojo_bin=str(fake_mojo), root=tmp_path, job=job, use_cache=True, cache_dir=cache_dir)
    assert ok3 is True
    assert "cache=hit" not in log3
    assert int(counter.read_text(encoding="utf-8")) == 2
    assert output.read_bytes() == b"pristine-2"

    linked_obj.write_bytes(b"obj-2")
    job_def = replace(job, defines=("FAST=2",))
    ok4, _ = compile_job(mojo_bin=str(fake_mojo), root=tmp_path, job=job_def, use_cache=True, cache_dir=cache_dir)
    assert ok4 is True
    assert int(counter.read_text(encoding="utf-8")) == 3
    assert output.read_bytes() == b"pristine-3"

    shutil.rmtree(cache_dir / RAW_CACHE_DIRNAME)
    ok5, log5 = compile_job(mojo_bin=str(fake_mojo), root=tmp_path, job=job_def, use_cache=True, cache_dir=cache_dir)
    assert ok5 is True
    assert "cache=hit" not in log5
    assert int(counter.read_text(encoding="utf-8")) == 4
    assert output.read_bytes() == b"pristine-4"
